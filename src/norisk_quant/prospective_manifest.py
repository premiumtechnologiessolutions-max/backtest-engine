"""FAC024 prospective source registration; metadata only, never upload quotes.

Tamper-evident manifest, not a trusted external timestamp or an independent
attestation that the passed DataFrame was parsed from the fingerprinted file.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import re

import numpy as np
import pandas as pd

START_MONTH = "2026-11"
END_MONTH = "2027-10"
EXPECTED_MONTHS = tuple(p.strftime("%Y-%m") for p in pd.period_range(START_MONTH, END_MONTH, freq="M"))
_REQUIRED_QUOTES = ("o", "h", "l", "c", "ao", "ah", "al", "ac")


def _utc_timestamp(value: object, label: str) -> pd.Timestamp:
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{label} must be a valid UTC timestamp") from exc
    if pd.isna(stamp) or stamp.tzinfo is None or str(stamp.tzinfo) != "UTC":
        raise ValueError(f"{label} must be explicitly UTC-aware")
    return stamp


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _month_bounds(month: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if month not in EXPECTED_MONTHS:
        raise ValueError("FAC024 month outside frozen prospective window")
    start = pd.Timestamp(month + "-01", tz="UTC")
    return start, start + pd.offsets.MonthBegin(1)


def hash_source_file(path: str | Path) -> tuple[str, int]:
    """Fingerprint exact local bytes; never upload the source."""
    digest = sha256()
    size = 0
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    if size == 0:
        raise ValueError("Empty prospective source partition")
    return digest.hexdigest(), size


def register_closed_month(
    month: str,
    path: str | Path,
    observed_minutes: pd.DataFrame,
    *,
    registered_at_utc: object,
    as_of_utc: object,
) -> dict:
    """Register a complete calendar month before examining trade outcomes.

    Caller must parse observed_minutes from the exact file at path. This
    function cannot independently prove that provenance relationship.
    """
    start, end = _month_bounds(month)
    registered = _utc_timestamp(registered_at_utc, "registered_at_utc")
    as_of = _utc_timestamp(as_of_utc, "as_of_utc")
    if registered < end or as_of < registered:
        raise ValueError("Prospective month must finish before source registration")
    if not isinstance(observed_minutes, pd.DataFrame) or observed_minutes.empty:
        raise ValueError("Observed M1 source must be nonempty")
    idx = observed_minutes.index
    if (not isinstance(idx, pd.DatetimeIndex) or idx.tz is None
            or str(idx.tz) != "UTC" or idx.hasnans or idx.has_duplicates
            or not idx.is_monotonic_increasing):
        raise ValueError("Observed M1 timestamps must be sorted unique UTC")
    if (idx[0] < start or idx[-1] >= end
            or (idx != idx.floor("min")).any()):
        raise ValueError("Observed M1 opens must be aligned and inside month")
    if not observed_minutes.columns.is_unique:
        raise ValueError("Observed BID/ASK column names must be unique")
    if any(k not in observed_minutes for k in _REQUIRED_QUOTES):
        raise ValueError("Observed source lacks BID/ASK OHLC")
    for col in _REQUIRED_QUOTES:
        dtype = observed_minutes[col].dtype
        if (not pd.api.types.is_numeric_dtype(dtype)
                or pd.api.types.is_bool_dtype(dtype)
                or pd.api.types.is_complex_dtype(dtype)):
            raise ValueError("BID/ASK OHLC must be real numeric, not bool, complex or text")
    values = observed_minutes[list(_REQUIRED_QUOTES)].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("BID/ASK OHLC must be finite positive")
    # The spread check alone cannot detect malformed high/low envelopes.
    # Reject impossible BID or ASK bars before recording a prospective source.
    for offset in (0, 4):
        op, hi, lo, cl = (values[:, offset + j] for j in range(4))
        if ((hi < np.maximum(op, cl)).any()
                or (lo > np.minimum(op, cl)).any()
                or (hi < lo).any()):
            raise ValueError("Invalid BID/ASK OHLC bar geometry")
    if (values[:, 4:] < values[:, :4]).any():
        raise ValueError("Crossed BID/ASK OHLC rejected")
    source_sha, source_bytes = hash_source_file(path)
    return {
        "month": month,
        "source_sha256": source_sha,
        "source_bytes": source_bytes,
        "observed_m1_rows": len(idx),
        "first_open_utc": idx[0].isoformat(),
        "last_open_utc": idx[-1].isoformat(),
        "registered_at_utc": registered.isoformat(),
    }


def _validate_record(record: dict) -> None:
    if not isinstance(record, dict) or set(record) != {
        "month", "source_sha256", "source_bytes", "observed_m1_rows",
        "first_open_utc", "last_open_utc", "registered_at_utc",
    }:
        raise ValueError("Unexpected or missing prospective record fields")
    start, end = _month_bounds(record["month"])
    if (not isinstance(record["source_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", record["source_sha256"])):
        raise ValueError("Invalid source SHA256")
    for field in ("source_bytes", "observed_m1_rows"):
        if type(record[field]) is not int or record[field] <= 0:
            raise ValueError("Invalid positive integer source metadata")
    first = _utc_timestamp(record["first_open_utc"], "first_open_utc")
    last = _utc_timestamp(record["last_open_utc"], "last_open_utc")
    registered = _utc_timestamp(record["registered_at_utc"], "registered_at_utc")
    if not (start <= first <= last < end <= registered):
        raise ValueError("Source timestamps violate closed-month boundaries")
    if first != first.floor("min") or last != last.floor("min"):
        raise ValueError("Source timestamps must be M1 aligned")
    slots = int((last - first) / pd.Timedelta(minutes=1)) + 1
    if record["observed_m1_rows"] > slots:
        raise ValueError("More M1 rows than possible distinct observed minutes")


def append_record(manifest: dict, record: dict) -> dict:
    """Append only the next chronological month, rejecting replacement."""
    verify_manifest(manifest)
    _validate_record(record)
    records = manifest["records"]
    if (len(records) >= len(EXPECTED_MONTHS)
            or record["month"] != EXPECTED_MONTHS[len(records)]):
        raise ValueError("Prospective source months must be appended once, in order")
    prior = records[-1]["record_digest"] if records else "0" * 64
    entry = {"record": dict(record), "previous_digest": prior}
    entry["record_digest"] = sha256(_canonical(entry)).hexdigest()
    return {"schema": "NRFX_FAC024_PROSPECTIVE_V1", "records": [*records, entry]}


def verify_manifest(manifest: dict) -> bool:
    if (not isinstance(manifest, dict) or set(manifest) != {"schema", "records"}
            or manifest["schema"] != "NRFX_FAC024_PROSPECTIVE_V1"
            or not isinstance(manifest["records"], list)
            or len(manifest["records"]) > len(EXPECTED_MONTHS)):
        raise ValueError("Invalid prospective manifest schema")
    previous = "0" * 64
    for i, entry in enumerate(manifest["records"]):
        if (not isinstance(entry, dict)
                or set(entry) != {"record", "previous_digest", "record_digest"}):
            raise ValueError("Invalid prospective chain entry")
        record = entry["record"]
        _validate_record(record)
        if record["month"] != EXPECTED_MONTHS[i] or entry["previous_digest"] != previous:
            raise ValueError("Out-of-order or broken prospective chain")
        expected = sha256(_canonical({"record": record, "previous_digest": previous})).hexdigest()
        if entry["record_digest"] != expected:
            raise ValueError("Prospective chain digest mismatch")
        previous = expected
    return True


def verify_partition_file(record: dict, path: str | Path) -> bool:
    _validate_record(record)
    digest, size = hash_source_file(path)
    if digest != record["source_sha256"] or size != record["source_bytes"]:
        raise ValueError("Prospective source bytes changed after registration")
    return True


def empty_manifest() -> dict:
    return {"schema": "NRFX_FAC024_PROSPECTIVE_V1", "records": []}


def all_months_registered(manifest: dict) -> bool:
    verify_manifest(manifest)
    return len(manifest["records"]) == len(EXPECTED_MONTHS)
