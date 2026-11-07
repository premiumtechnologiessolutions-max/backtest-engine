"""FAC025-ENTRY-A: conservative source-M1 next-open *candidate* preflight.

This is NOT a fill simulator, strategy result, shared portfolio backtest, or
proof of source authenticity. An observed next BID/ASK open is only a candidate;
execution, fees, gap-through and mark-to-market require the canonical engine.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

try:
    from scripts.research_fac025_frozen_entry_policy import POLICY_SHA256
    from scripts.research_fac025_bidask_receipt import FIELDS as PAIRED_FIELDS
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from research_fac025_frozen_entry_policy import POLICY_SHA256
    from research_fac025_bidask_receipt import FIELDS as PAIRED_FIELDS

MINUTE = timedelta(minutes=1)
MAX_ROWS = 100_000


def _utc(value: object, name: str) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise ValueError(f"{name} must be a UTC-aware datetime")
    return value.astimezone(timezone.utc)


def _positive(value: object, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite positive numeric")
    return float(value)


def _observed_row(row: object) -> tuple[datetime, float, float]:
    """Reject incomplete, crossed, non-chronological or fabricated OHLC."""
    if type(row) is not dict or row.keys() != PAIRED_FIELDS:
        raise ValueError("Malformed paired source M1 row")
    opened = _utc(row["open_at"], "M1 open_at")
    if opened.second or opened.microsecond:
        raise ValueError("Source M1 open is not minute-aligned")
    for side in ("bid", "ask"):
        prices = {k: _positive(row[f"{side}_{k}"], f"{side}_{k}")
                  for k in ("open", "high", "low", "close")}
        if not prices["low"] <= min(prices["open"], prices["close"]) <= max(
                prices["open"], prices["close"]) <= prices["high"]:
            raise ValueError("Inconsistent source M1 OHLC")
    if any(row[f"ask_{k}"] < row[f"bid_{k}"]
           for k in ("open", "high", "low", "close")):
        raise ValueError("Crossed paired source M1 quotes")
    for side in ("bid", "ask"):
        receipt = _utc(row[f"{side}_received_at"], f"{side} receipt")
        if receipt < opened + MINUTE:
            raise ValueError("Completed M1 receipt precedes candle end")
    return opened, float(row["bid_open"]), float(row["ask_open"])


def preflight_next_observed_open(
    intent: dict, observed_future_m1: list[dict], *,
    capacity_free_at_signal: bool | None = None,
) -> dict:
    """Identify the FIRST observed post-signal open within the frozen 60s.

    The caller must separately authenticate quote origin, receipt provenance,
    and the one-slot portfolio state at decision time. No price is a fill.
    Capacity is intentionally *never* marked independently verified here.
    A missing first eligible M1 cannot be synthesized or replaced by a later
    out-of-window open. No intrabar OHLC may be used to decide the entry.
    """
    if type(intent) is not dict or intent.get("status") != "RESEARCH_INTENT_ONLY":
        raise ValueError("Requires frozen research intent, not a trade")
    if (intent.get("frozen_entry_policy") != "FAC025-ENTRY-A"
            or intent.get("policy_sha256") != POLICY_SHA256
            or intent.get("execution") != "RESEARCH_INTENT_ONLY_NO_FILLS_NO_ORDERS"
            or intent.get("max_entry_delay_seconds") != 60
            or intent.get("shared_capacity_slots") != 1):
        raise ValueError("Intent is not the frozen FAC025-ENTRY-A policy")
    if intent.get("side") not in ("BUY", "SELL"):
        raise ValueError("Invalid intent side")
    if type(intent.get("signal_at")) is not str:
        raise ValueError("Missing frozen signal timestamp")
    try:
        signal = _utc(datetime.fromisoformat(intent["signal_at"]), "signal_at")
        deadline = _utc(datetime.fromisoformat(intent["entry_deadline_utc"]), "deadline")
    except (KeyError, TypeError) as exc:
        raise ValueError("Missing frozen entry deadline") from exc
    if deadline - signal != MINUTE:
        raise ValueError("Frozen entry deadline was modified")
    if type(observed_future_m1) is not list or len(observed_future_m1) > MAX_ROWS:
        raise ValueError("Observed M1 must be a bounded list")
    if capacity_free_at_signal is not None and type(capacity_free_at_signal) is not bool:
        raise ValueError("Capacity confirmation must be explicit boolean")
    base = {
        "status": "BLOCKED", "reason": "CAPACITY_NOT_CONFIRMED_AT_SIGNAL",
        "source_authenticated": False, "capacity_independently_verified": False,
        "canonical_execution_verified": False, "entry_fill": "N/A",
        "monthly_net_pnl_usd_per_oz": "N/A", "floating_m1_drawdown": "N/A",
        "execution": "SOURCE_OPEN_CANDIDATE_ONLY_NO_FILLS_NO_ORDERS",
    }
    if capacity_free_at_signal is not True:
        return base
    first = None
    previous = None
    for row in observed_future_m1:
        opened, bid, ask = _observed_row(row)
        if previous is not None and opened <= previous:
            raise ValueError("Source M1 must be strictly ordered and unique")
        if opened <= signal:
            raise ValueError("Source entry candidate must open AFTER decision")
        previous = opened
        if first is None:
            first = (opened, bid, ask)
    if first is None or first[0] > deadline:
        base["reason"] = "NO_OBSERVED_OPEN_WITHIN_FROZEN_60_SECONDS"
        return base
    opened, bid, ask = first
    base.update({
        "status": "CANDIDATE_NOT_FILL", "reason": "FIRST_OBSERVED_POST_SIGNAL_OPEN",
        "candidate_open_at_utc": opened.isoformat(),
        "candidate_side": intent["side"],
        "candidate_quote_side": "ASK" if intent["side"] == "BUY" else "BID",
        "candidate_observed_open_usd_per_oz": ask if intent["side"] == "BUY" else bid,
        "entry_delay_seconds": (opened - signal).total_seconds(),
    })
    return base
