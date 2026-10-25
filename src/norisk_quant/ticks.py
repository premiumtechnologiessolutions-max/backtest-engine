"""Explicit real-tick ingest and strict provenance gates.

A native M1 OHLC collection is NOT a real-tick feed. Never auto-generate
ticks and label them as observed market events.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TickSource:
    """External source metadata; 'declared' is NOT independently verified."""

    provider: str
    symbol: str
    timezone: str = "UTC"
    source_kind: str = "declared_broker_ticks"
    data_license: str = "unknown"

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.symbol.strip():
            raise ValueError("Tick source must name provider and symbol")
        if self.source_kind not in ("declared_broker_ticks", "exchange_ticks", "synthetic"):
            raise ValueError("Unrecognized source_kind")
        if self.timezone != "UTC":
            raise ValueError("Only UTC input timestamps are accepted")


def normalize_ticks(
    raw: pd.DataFrame,
    source: TickSource,
    *,
    allow_synthetic: bool = False,
) -> pd.DataFrame:
    """Validate quote ticks with exact UTC event timestamps.

    Required columns: ts_utc ISO8601 with Z/offset, bid, ask.
    If two events have identical UTC timestamps, an explicit increasing seq
    is REQUIRED. Arrival order without seq cannot establish their order.
    Returned index remains UTC DatetimeIndex. No forward-filling, no OHLC
    interpolation, and no conversion of minute bars into imaginary ticks.
    """
    if source.source_kind == "synthetic" and not allow_synthetic:
        raise ValueError("Synthetic ticks cannot be used in strict real-tick mode")
    cols = {"ts_utc", "bid", "ask"}
    if not cols.issubset(raw.columns):
        raise ValueError(f"Tick data missing columns: {sorted(cols - set(raw.columns))}")
    if raw.empty:
        raise ValueError("Empty tick dataset")
    result = raw.copy()
    # Reject naive strings instead of assuming provider machine timezone.
    text = result["ts_utc"].astype(str)
    if not text.str.contains(r"(Z|[+-]\d\d:\d\d)$", regex=True).all():
        raise ValueError("Every tick timestamp must explicitly specify UTC offset/Z")
    result["ts_utc"] = pd.to_datetime(text, utc=True, errors="raise", format="ISO8601")
    result["bid"] = pd.to_numeric(result["bid"], errors="raise")
    result["ask"] = pd.to_numeric(result["ask"], errors="raise")
    if (
        not np.isfinite(result[["bid", "ask"]].to_numpy(dtype=float)).all()
        or (result["bid"] <= 0).any()
        or (result["ask"] <= 0).any()
        or (result["ask"] < result["bid"]).any()
    ):
        raise ValueError("Invalid bid/ask tick quote")
    duplicates = result["ts_utc"].duplicated(keep=False)
    if duplicates.any():
        if "seq" not in result.columns or result["seq"].isna().any():
            raise ValueError("Same-timestamp ticks require a non-null sequence field")
        result["seq"] = pd.to_numeric(result["seq"], errors="raise")
        if result["seq"].isna().any() or (result["seq"] % 1 != 0).any():
            raise ValueError("Sequence must contain integer event indices")
        if result.duplicated(subset=["ts_utc", "seq"]).any():
            raise ValueError("Duplicate timestamp/sequence pair")
        # Sorting is stable and uses source-provided order, never bid price.
        result = result.sort_values(["ts_utc", "seq"], kind="stable")
    else:
        result = result.sort_values(["ts_utc"], kind="stable")
    result = result.set_index("ts_utc")
    result.index.name = "ts_utc"
    result.attrs["source_provider"] = source.provider
    result.attrs["source_kind"] = source.source_kind
    result.attrs["quote_provenance_declared_not_verified"] = True
    return result


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_tick_csv(
    path: str | Path, source: TickSource, *, strict_real: bool = True
) -> dict:
    """Audit a tick CSV and its SHA-256; DO NOT label it authenticated data."""
    path = Path(path)
    if path.suffix.lower() != ".csv":
        raise ValueError("Only explicit raw tick CSV is supported")
    ticks = normalize_ticks(pd.read_csv(path), source, allow_synthetic=not strict_real)
    intervals = ticks.index.to_series().diff().dt.total_seconds().dropna()
    observed_minutes = ticks.index.floor("min").nunique()
    return {
        "format_version": 1,
        "source_file_sha256": _hash(path),
        "source_provider_declared": source.provider,
        "symbol": source.symbol,
        "source_kind_declared": source.source_kind,
        "source_authentication": "NOT_VERIFIED",
        "rows": int(len(ticks)),
        "observed_minutes": int(observed_minutes),
        "start_utc": ticks.index[0].isoformat(),
        "end_utc": ticks.index[-1].isoformat(),
        "max_inter_event_seconds": float(intervals.max()) if not intervals.empty else None,
        "zero_or_negative_spreads": int((ticks["ask"] <= ticks["bid"]).sum()),
        "note": "Quote ticks do not imply executable fills; broker contract and provider validation remain separate.",
    }


def compare_tick_bid_to_m1(ticks: pd.DataFrame, minute_bid: pd.DataFrame, *,
                           tolerance: float = 1e-6) -> pd.DataFrame:
    """Audit real-tick BID OHLC against source BID M1 on OBSERVED minutes only.

    Differences can arise from distinct feed sources. This reports them
    without deciding which source is right or manufacturing missing ticks.
    """
    if tolerance < 0:
        raise ValueError("tolerance cannot be negative")
    if ticks.empty:
        raise ValueError("Empty tick data")
    if not isinstance(ticks.index, pd.DatetimeIndex) or ticks.index.tz is None:
        raise ValueError("Ticks need UTC-aware DatetimeIndex")
    if not isinstance(minute_bid.index, pd.DatetimeIndex) or minute_bid.index.tz is None:
        raise ValueError("M1 bars need UTC-aware DatetimeIndex")
    required = {"o", "h", "l", "c"}
    if not required.issubset(minute_bid.columns):
        raise ValueError("BID M1 OHLC columns missing")
    actual = ticks["bid"].resample("1min").ohlc().rename(
        columns={"open": "o", "high": "h", "low": "l", "close": "c"}
    ).dropna()
    compare = minute_bid[list(("o", "h", "l", "c"))].join(
        actual, how="left", rsuffix="_tick"
    )
    compare["tick_present"] = compare["o_tick"].notna()
    differences = [
        (compare[name] - compare[f"{name}_tick"]).abs()
        for name in ("o", "h", "l", "c")
    ]
    compare["max_bid_ohlc_diff"] = pd.concat(differences, axis=1).max(axis=1)
    compare["mismatch"] = compare["tick_present"] & (compare["max_bid_ohlc_diff"] > tolerance)
    return compare[["tick_present", "max_bid_ohlc_diff", "mismatch"]]


def ensure_tick_capability(*, tick_audit: dict | None, claimed_mode: str) -> None:
    """Fail closed when high-fidelity tick replay is requested without evidence."""
    if claimed_mode not in ("m1_conservative", "observed_tick_research"):
        raise ValueError("Unsupported backtest mode")
    if claimed_mode == "observed_tick_research":
        if not tick_audit or tick_audit.get("rows", 0) <= 0:
            raise ValueError("Observed-tick mode requires independent tick input and audit")
        if tick_audit.get("source_kind_declared") == "synthetic":
            raise ValueError("Synthetic ticks cannot satisfy real-tick requirement")
        if not tick_audit.get("source_file_sha256"):
            raise ValueError("Missing SHA-256 tick provenance")
