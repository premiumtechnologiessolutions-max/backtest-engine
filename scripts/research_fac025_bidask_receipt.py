"""FAC025 paired BID/ASK receipt preflight; research-only, no fills or orders.

A caller must supply synchronized, independently received minute OHLC for both
quote sides. Close-spread observations are NOT executable entry/exit spreads.
This adapter never changes the frozen FAC025 parameters or estimates P/L.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from statistics import median

try:
    from scripts.research_fac025_receipt_gate import (
        MAX_INPUT_M1, evaluate_gate_from_received_inputs,
    )
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from research_fac025_receipt_gate import (
        MAX_INPUT_M1, evaluate_gate_from_received_inputs,
    )

FIELDS = frozenset({
    "open_at", "bid_open", "bid_high", "bid_low", "bid_close",
    "ask_open", "ask_high", "ask_low", "ask_close",
    "bid_received_at", "ask_received_at",
})
MINUTE = timedelta(minutes=1)


def _utc(value: object, label: str) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise ValueError(f"{label} must be UTC-aware datetime")
    return value.astimezone(timezone.utc)


def _price(value: object, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite positive numeric, not boolean")
    return float(value)


def evaluate_gate_from_paired_received_quotes(
    signal_at: datetime, paired_m1: list[dict], confirmed_trades: list[dict],
    *, lookback: int = 4, **frozen_gate_parameters: object,
) -> dict:
    """Audit BOTH quote sides and receipts before passing BID context to FAC025.

    Every pair represents the same complete UTC M1 interval. All four
    synchronized ASK OHLC extrema must be >= BID counterparts; this requires
    the caller's BID/ASK bars to use matching tick coverage. Incomplete or
    differently aggregated feeds fail closed, not silently resampled.
    """
    now = _utc(signal_at, "signal_at")
    if type(paired_m1) is not list or len(paired_m1) > MAX_INPUT_M1:
        raise ValueError("Paired M1 input must be a bounded list")
    verified_bid = []
    close_spreads = []
    for row in paired_m1:
        if type(row) is not dict or row.keys() != FIELDS:
            raise ValueError("Malformed paired BID/ASK M1 row")
        opened = _utc(row["open_at"], "M1 open_at")
        bid = {k: _price(row["bid_" + k], "bid_" + k)
               for k in ("open", "high", "low", "close")}
        ask = {k: _price(row["ask_" + k], "ask_" + k)
               for k in ("open", "high", "low", "close")}
        for side, prices in (("BID", bid), ("ASK", ask)):
            if not prices["low"] <= min(prices["open"], prices["close"]) <= max(
                    prices["open"], prices["close"]) <= prices["high"]:
                raise ValueError(f"Inconsistent {side} M1 OHLC")
        if any(ask[k] < bid[k] for k in ("open", "high", "low", "close")):
            raise ValueError("Crossed synchronized BID/ASK OHLC")
        bid_received = _utc(row["bid_received_at"], "bid_received_at")
        ask_received = _utc(row["ask_received_at"], "ask_received_at")
        if min(bid_received, ask_received) < opened + MINUTE:
            raise ValueError("Completed paired OHLC receipt precedes M1 close")
        if max(bid_received, ask_received) >= now:
            raise ValueError("Paired quote receipt at/after signal is not causal")
        verified_bid.append({
            "open_at": opened, **bid,
            "received_at": max(bid_received, ask_received),
        })
        close_spreads.append(ask["close"] - bid["close"])
    gate = evaluate_gate_from_received_inputs(
        now, verified_bid, confirmed_trades, lookback=lookback,
        **frozen_gate_parameters,
    )
    return {
        "gate": gate,
        "quote_side_used_for_context": "BID",
        "paired_complete_m1": len(verified_bid),
        "observed_close_spread_usd_per_oz": (
            {"minimum": min(close_spreads), "median": median(close_spreads),
             "maximum": max(close_spreads)} if close_spreads else None
        ),
        "receipt_provenance": "CALLER_SUPPLIED_NOT_INDEPENDENTLY_AUTHENTICATED",
        "execution": "RESEARCH_ONLY_NO_FILLS_NO_ORDERS",
    }
