"""Preregistered research-only causal session/volatility/loss gate (FAC025).

This pure function never submits orders, reads future observations, or claims
profitability. Input bars must be complete, observed UTC M15 bars; trade net
values must already be verified AFTER all canonical fees. Missing M1 is never
interpolated. Position sizing is intentionally not performed here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
STEP = timedelta(minutes=15)
MAX_STALENESS = timedelta(minutes=1)


def _utc(value: object, label: str) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise ValueError(f"{label} must be a UTC-aware datetime")
    return value.astimezone(timezone.utc)


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite numeric, not boolean")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")
    return float(value)


def evaluate_causal_gate(
    signal_at: datetime, bars: list[dict], closed_trades: list[dict], *,
    lookback: int = 4, min_range_ratio: float = 0.0002,
    max_range_ratio: float = 0.03, daily_loss_halt: float = 3.0,
    session_start_hour: int = 8, session_end_hour: int = 12,
) -> dict:
    """Evaluate only already closed M15 bars and already closed trades.

    Bars: end_at, high, low, close, observed_m1_count. Trades: closed_at,
    net_usd_per_oz (AFTER verified $0.40/oz roundtrip). Both chronological.
    Signal is evaluated at a UTC instant, no more than 60 seconds after the
    last complete M15 bar. Session hours are local New York (DST-aware).
    """
    now = _utc(signal_at, "signal_at")
    if type(lookback) is not int or not 2 <= lookback <= 32:
        raise ValueError("lookback must be integer 2..32")
    low_ratio = _number(min_range_ratio, "min_range_ratio", positive=True)
    high_ratio = _number(max_range_ratio, "max_range_ratio", positive=True)
    halt = _number(daily_loss_halt, "daily_loss_halt", positive=True)
    if low_ratio >= high_ratio or high_ratio > 1:
        raise ValueError("Invalid frozen volatility interval")
    if (type(session_start_hour) is not int or type(session_end_hour) is not int
            or not 0 <= session_start_hour < session_end_hour <= 24):
        raise ValueError("Invalid New York session hours")
    if type(bars) is not list or type(closed_trades) is not list:
        raise ValueError("Bars and trades must be ordered lists")

    observed = []
    previous = None
    for bar in bars:
        if type(bar) is not dict or set(bar) != {
            "end_at", "high", "low", "close", "observed_m1_count"
        }:
            raise ValueError("Malformed observed M15 bar")
        end = _utc(bar["end_at"], "bar end")
        if end > now or (previous is not None and end <= previous):
            raise ValueError("Future or out-of-order M15 bar")
        if end.second or end.microsecond or end.minute % 15:
            raise ValueError("M15 bar end not on UTC quarter-hour")
        high = _number(bar["high"], "high", positive=True)
        low = _number(bar["low"], "low", positive=True)
        close = _number(bar["close"], "close", positive=True)
        if not low <= close <= high:
            raise ValueError("Inconsistent observed M15 OHLC")
        if type(bar["observed_m1_count"]) is not int or not 0 <= bar["observed_m1_count"] <= 15:
            raise ValueError("Invalid observed M1 count")
        observed.append((end, high - low, close, bar["observed_m1_count"]))
        previous = end

    today = now.astimezone(NY).date()
    realized = 0.0
    previous_close = None
    for trade in closed_trades:
        if type(trade) is not dict or set(trade) != {"closed_at", "net_usd_per_oz"}:
            raise ValueError("Malformed verified closed-trade record")
        closed = _utc(trade["closed_at"], "trade close")
        # Validate value before temporal causality, even for a malformed
        # same-instant/future record. A trade closing at the exact signal
        # timestamp is not provably known when that signal is decided.
        pnl = _number(trade["net_usd_per_oz"], "net_usd_per_oz")
        if closed >= now or (previous_close is not None and closed < previous_close):
            raise ValueError("Trade close must be strictly before signal and chronologically ordered")
        if closed.astimezone(NY).date() == today:
            realized += pnl
        previous_close = closed

    if not math.isfinite(realized):
        raise ValueError("Nonfinite cumulative realized P/L")

    result = {
        "status": "BLOCKED", "reason": None, "observed_bars": len(observed),
        "range_ratio": None, "realized_today_usd_per_oz": round(realized, 8),
        "session_timezone": "America/New_York",
        "execution": "RESEARCH_GATE_ONLY_NO_ORDER",
    }
    def block(reason: str) -> dict:
        result["reason"] = reason
        return result

    local_hour = now.astimezone(NY).hour
    if not session_start_hour <= local_hour < session_end_hour:
        return block("OUTSIDE_FROZEN_NY_SESSION")
    if realized <= -halt:
        return block("PREKNOWN_REALIZED_DAILY_LOSS_HALT")
    if len(observed) < lookback:
        return block("INSUFFICIENT_OBSERVED_M15")
    window = observed[-lookback:]
    if any(item[3] != 15 for item in window):
        return block("INCOMPLETE_OBSERVED_M15")
    if any(b[0] - a[0] != STEP for a, b in zip(window, window[1:])):
        return block("MARKET_GAP_NO_SYNTHETIC_BARS")
    if not timedelta(0) <= now - window[-1][0] <= MAX_STALENESS:
        return block("STALE_COMPLETED_M15_CONTEXT")
    ratio = sum(item[1] for item in window) / (lookback * window[-1][2])
    if not math.isfinite(ratio):
        raise ValueError("Nonfinite normalized observed range")
    result["range_ratio"] = round(ratio, 12)
    if ratio < low_ratio or ratio > high_ratio:
        return block("OUTSIDE_FROZEN_VOLATILITY_REGIME")
    result["status"] = "ELIGIBLE_RESEARCH_ONLY"
    result["reason"] = "CAUSAL_FILTERS_PASSED_NOT_PROFITABILITY_EVIDENCE"
    return result
