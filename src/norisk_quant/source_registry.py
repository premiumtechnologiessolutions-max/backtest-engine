"""NoRiskFX Data Hub: fail-closed, source-scoped evidence *metadata* registry.

This intentionally does not read raw quote files, connect to brokers, infer DST,
merge feeds, rerun strategies, or grant execution/OOS approval. It accepts
previously validated research evidence from the canonical Gold M1 engine and
the separate private Terminal v0.19.1 intake (PR #5); quote bytes stay private.

The registry is pure and has no filesystem/database side effects. Callers own
durable storage, access controls, encryption and source retention.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Any, Literal

SCHEMA = "NRFX_UNIFIED_DATA_HUB_SOURCE_V1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._+/:·\-]{0,119}\Z")
_SYMBOL = re.compile(r"[A-Z]{6}(?:[-._][A-Za-z0-9]{1,16})?\Z")
_CURRENCY = re.compile(r"[A-Z]{3}\Z")
_ASSETS = frozenset(("XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
                     "NZDUSD", "USDCAD", "USDCHF"))
_TICK_KEYS = frozenset((
    "schema_version", "source_bytes_sha256", "quote_context_sha256",
    "provider_declared", "symbol_declared", "source_kind_declared",
    "source_authentication", "account_currency_label", "quote_currency_label",
    "ticks", "first_utc", "last_utc", "cost_model", "execution",
    "simulation_results_imported", "independent_oos", "broker_fill_parity", "notice",
))
_MANIFEST_KEYS = frozenset((
    "source_file_sha256", "observed_slice_sha256", "rows",
    "first_utc", "last_utc", "origin",
))
DataFamily = Literal["original_gold_m1_bidask", "private_terminal_bidask_ticks"]


def _text(value: object, name: str, *, expression: re.Pattern[str] = _SOURCE) -> str:
    if type(value) is not str or not expression.fullmatch(value):
        raise ValueError(f"Invalid source metadata: {name}")
    return value


def _sha(value: object, name: str) -> str:
    return _text(value, name, expression=_SHA)


def _count(value: object, name: str) -> int:
    if type(value) is not int or value <= 0 or value > 2_000_000_000:
        raise ValueError(f"Invalid {name}: must be a positive integer")
    return value


def _instant(value: object, name: str) -> datetime:
    # Precisely UTC ISO8601, no local/GMT+3 or naive server time.
    if type(value) is not str or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value
    ):
        raise ValueError(f"{name} requires an explicitly normalized UTC timestamp")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid UTC {name}") from exc
    if moment.utcoffset() != timezone.utc.utcoffset(moment):
        raise ValueError(f"{name} is not UTC")
    return moment.astimezone(timezone.utc)


def _identity(record: dict[str, Any]) -> str:
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("ascii")
    return sha256(b"NRFX_DATA_HUB_RECORD_V1\x00" + raw).hexdigest()


@dataclass(frozen=True)
class SourceRecord:
    family: DataFamily
    asset: str
    instrument: str
    provider_declared: str
    quote_currency: str
    account_currency: str | None
    rows: int
    first_utc: str
    last_utc: str
    source_file_sha256: str
    observed_quote_sha256: str
    source_authentication: Literal["NOT_VERIFIED"]
    access: Literal["PRIVATE_LOCAL_ONLY"]
    data_rights: Literal["UNVERIFIED"]
    execution: Literal["NONE"]
    cost_policy: Literal["NO_COST_AT_DATA_LAYER"]
    independent_oos: Literal[False]
    id: str

    def internal_manifest(self) -> dict[str, Any]:
        """Internal audit only; account-independent provider label isn't public."""
        fields = {name: getattr(self, name) for name in _FIELDS}
        return {"schema": SCHEMA, "record": fields, "id": self.id}

    def public_summary(self) -> dict[str, Any]:
        """Safe descriptive status. No file hash, source scope or quote prices."""
        return {
            "schema": SCHEMA, "manifest_id": self.id,
            "family": self.family, "asset": self.asset, "rows": self.rows,
            "first_utc": self.first_utc, "last_utc": self.last_utc,
            "source_authentication": self.source_authentication,
            "access": self.access, "execution": self.execution,
            "independent_oos": False, "data_rights": self.data_rights,
        }


_FIELDS = tuple(name for name in SourceRecord.__dataclass_fields__ if name != "id")


def _make_record(*, family: DataFamily, asset: str, instrument: str,
                 provider_declared: str, quote_currency: str,
                 account_currency: str | None, rows: int,
                 first_utc: str, last_utc: str, source_file_sha256: str,
                 observed_quote_sha256: str) -> SourceRecord:
    _text(asset, "asset")
    if asset not in _ASSETS or (family == "original_gold_m1_bidask" and asset != "XAUUSD"):
        raise ValueError("Unrecognized or unsupported asset")
    _text(instrument, "instrument", expression=_SYMBOL)
    if not (instrument == asset or re.match(re.escape(asset) + r"[-._]", instrument)):
        raise ValueError("Instrument is not bound to the declared asset")
    _text(provider_declared, "provider")
    _text(quote_currency, "quote_currency", expression=_CURRENCY)
    if quote_currency != ("USD" if asset == "XAUUSD" else asset[3:]):
        raise ValueError("Quote currency does not match the asset")
    if account_currency is not None:
        _text(account_currency, "account_currency", expression=_CURRENCY)
    count = _count(rows, "source row count")
    first, last = _instant(first_utc, "first_utc"), _instant(last_utc, "last_utc")
    if first > last or (first == last and count > 1 and family == "original_gold_m1_bidask"):
        raise ValueError("Impossible source observation interval")
    if first.year < 1970 or last.year > 2100:
        raise ValueError("Unsupported market observation period")
    if family == "original_gold_m1_bidask" and (
        first.second or first.microsecond or last.second or last.microsecond
    ):
        raise ValueError("Source M1 candles must be aligned to minute opens")
    if family == "private_terminal_bidask_ticks" and count < 2:
        raise ValueError("Terminal quote evidence needs at least two tick observations")

    values = dict(family=family, asset=asset, instrument=instrument,
                  provider_declared=provider_declared, quote_currency=quote_currency,
                  account_currency=account_currency, rows=count,
                  first_utc=first.isoformat(), last_utc=last.isoformat(),
                  source_file_sha256=_sha(source_file_sha256, "source_file_sha256"),
                  observed_quote_sha256=_sha(observed_quote_sha256, "observed_quote_sha256"),
                  source_authentication="NOT_VERIFIED", access="PRIVATE_LOCAL_ONLY",
                  data_rights="UNVERIFIED", execution="NONE",
                  cost_policy="NO_COST_AT_DATA_LAYER", independent_oos=False)
    return SourceRecord(**values, id=_identity(values))


def register_original_gold_m1(metadata: dict[str, Any]) -> SourceRecord:
    """Index exact source M1 fingerprints; do not infer tick-level event order."""
    if type(metadata) is not dict or set(metadata) != _MANIFEST_KEYS:
        raise ValueError("Original Gold M1 metadata has missing or extra keys")
    if metadata["origin"] != "user_supplied_gold_m1_bidask":
        raise ValueError("Original M1 origin must be explicitly declared")
    return _make_record(
        family="original_gold_m1_bidask", asset="XAUUSD", instrument="XAUUSD",
        provider_declared="User-supplied BID ASK M1 source",
        quote_currency="USD", account_currency=None,
        rows=metadata["rows"], first_utc=metadata["first_utc"],
        last_utc=metadata["last_utc"],
        source_file_sha256=metadata["source_file_sha256"],
        observed_quote_sha256=metadata["observed_slice_sha256"],
    )


def register_terminal_tick_evidence(evidence: dict[str, Any], *,
                                    permit_synthetic: bool = False) -> SourceRecord:
    """Accept ONLY exact metadata produced by the B01 read-only intake adapter.

    The producer itself does not authenticate the provider or guarantee
    execution. This layer intentionally never receives raw ticks or account IDs.
    """
    if type(evidence) is not dict or set(evidence) != _TICK_KEYS:
        raise ValueError("Terminal evidence schema mismatch or private fields present")
    expected = {
        "schema_version": "noriskfx-terminal-tick-import-v1",
        "source_authentication": "NOT_VERIFIED",
        "cost_model": "NOT_APPLIED_DATA_ONLY",
        "execution": "NONE_RESEARCH_IMPORT",
        "simulation_results_imported": False,
        "independent_oos": False,
        "broker_fill_parity": False,
    }
    for field, value in expected.items():
        if type(evidence[field]) is not type(value) or evidence[field] != value:
            raise ValueError(f"Untrusted Terminal claim or unsupported contract: {field}")
    kind = evidence["source_kind_declared"]
    if kind != "broker_history" and not (permit_synthetic and kind == "synthetic_test"):
        raise ValueError("Synthetic or unknown Terminal quote source not permitted")
    _text(evidence["notice"], "notice", expression=re.compile(r"[\x20-\x7e]{1,300}\Z"))
    instrument = _text(evidence["symbol_declared"], "symbol_declared", expression=_SYMBOL)
    asset = instrument[:6]
    return _make_record(
        family="private_terminal_bidask_ticks", asset=asset,
        instrument=instrument, provider_declared=evidence["provider_declared"],
        quote_currency=evidence["quote_currency_label"],
        account_currency=evidence["account_currency_label"],
        rows=evidence["ticks"], first_utc=evidence["first_utc"],
        last_utc=evidence["last_utc"],
        source_file_sha256=evidence["source_bytes_sha256"],
        observed_quote_sha256=evidence["quote_context_sha256"],
    )


def verify_record_manifest(manifest: dict[str, Any]) -> SourceRecord:
    """Fail closed on modified fields, malformed IDs and noncanonical JSON."""
    if type(manifest) is not dict or set(manifest) != {"schema", "record", "id"} or manifest["schema"] != SCHEMA:
        raise ValueError("Invalid Data Hub manifest envelope")
    record = manifest["record"]
    if type(record) is not dict or set(record) != set(_FIELDS):
        raise ValueError("Invalid Data Hub record fields")
    if _sha(manifest["id"], "manifest id") != _identity(record):
        raise ValueError("Data Hub manifest identity mismatch")
    # Rebuild with a strictly defined field set; never trust serialized flags.
    accepted = _make_record(**{k: record[k] for k in (
        "family", "asset", "instrument", "provider_declared", "quote_currency",
        "account_currency", "rows", "first_utc", "last_utc",
        "source_file_sha256", "observed_quote_sha256",
    )})
    if accepted.internal_manifest() != manifest:
        raise ValueError("A Data Hub authorization/status field was changed")
    return accepted


class SourceRegistry:
    """In-memory, strict idempotent source manifest catalog (not a data lake)."""

    def __init__(self) -> None:
        self._records: dict[str, SourceRecord] = {}

    def add(self, record: SourceRecord) -> str:
        # Revalidate even if caller constructed a SourceRecord manually.
        clean = verify_record_manifest(record.internal_manifest())
        prior = self._records.get(clean.id)
        if prior is not None and prior != clean:
            raise ValueError("Dataset manifest identity collision")
        self._records[clean.id] = clean
        return clean.id

    def get(self, record_id: str) -> SourceRecord:
        _sha(record_id, "source record id")
        return self._records[record_id]

    def summaries(self) -> list[dict[str, Any]]:
        return [self._records[key].public_summary() for key in sorted(self._records)]


def compare_source_windows(a: SourceRecord, b: SourceRecord) -> dict[str, Any]:
    """Observational comparison ONLY; never concatenate or certify feeds."""
    a = verify_record_manifest(a.internal_manifest())
    b = verify_record_manifest(b.internal_manifest())
    overlap = max(a.first_utc, b.first_utc) <= min(a.last_utc, b.last_utc)
    same_asset = a.asset == b.asset
    same_currency = a.quote_currency == b.quote_currency
    return {
        "left": a.id, "right": b.id,
        "same_asset": same_asset,
        "same_quote_currency": same_currency,
        "time_intersection": overlap,
        "can_compare_quote_observations": same_asset and same_currency and overlap,
        "can_merge_as_one_market_feed": False,
        "can_establish_broker_fill_parity": False,
        "notice": "Different source/trading models must remain distinct. Observational comparison is not execution parity.",
    }
