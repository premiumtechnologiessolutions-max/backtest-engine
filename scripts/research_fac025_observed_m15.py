"""FAC025 observed-M1-only M15 construction and causal research gate adapter.

No execution, synthetic interpolation, broker connection, or trading signals.
Input is a caller-frozen chronological M1 single quote-side OHLC stream;
open_at is the UTC minute OPEN, not the close or an arrival timestamp.
A separate trusted feed availability/publish-time audit remains mandatory.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

try:
    from scripts.research_causal_session_risk import evaluate_causal_gate
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from research_causal_session_risk import evaluate_causal_gate

ONE_MINUTE = timedelta(minutes=1)
FIFTEEN_MINUTES = timedelta(minutes=15)
FIELDS = frozenset({"open_at", "open", "high", "low", "close"})
MAX_INPUT_M1 = 100_000


def _utc(value: object, label: str) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise ValueError(f"{label} must be UTC-aware datetime")
    return value.astimezone(timezone.utc)


def _price(value: object, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be finite positive numeric, not boolean")
    return float(value)


def reconstruct_observed_m15(m1_rows: list[dict], signal_at: datetime, *,
                              lookback: int = 4) -> list[dict]:
    """Reconstruct chronological M15 bars from genuine, complete, preknown M1.

    Reject unaligned, duplicated, future, in-progress or inconsistent rows.
    A missing M1 is never fabricated: it decreases observed_m1_count.
    A wholly missing M15 remains absent, allowing the gate to reject gaps.
    Every M15 interval must end STRICTLY before the decision timestamp.
    """
    now = _utc(signal_at, "signal_at")
    if type(lookback) is not int or not 2 <= lookback <= 32:
        raise ValueError("lookback must be integer 2..32")
    if type(m1_rows) is not list or len(m1_rows) > MAX_INPUT_M1:
        raise ValueError("M1 input must be a bounded chronological list")
    observed: list[dict] = []
    previous: datetime | None = None
    for row in m1_rows:
        if type(row) is not dict or row.keys() != FIELDS:
            raise ValueError("Malformed observed M1 OHLC row")
        opened = _utc(row["open_at"], "M1 open_at")
        if opened.second or opened.microsecond:
            raise ValueError("M1 open_at must align to an exact UTC minute")
        if previous is not None and opened <= previous:
            raise ValueError("M1 opens must be strictly increasing and unique")
        if opened + ONE_MINUTE >= now:
            raise ValueError("M1 close at or after signal is not preknown")
        previous = opened
        start = opened.replace(minute=opened.minute // 15 * 15)
        end = start + FIFTEEN_MINUTES
        if end >= now:
            raise ValueError("Incomplete or same-instant M15 is not preknown")
        o = _price(row["open"], "M1 open")
        h = _price(row["high"], "M1 high")
        l = _price(row["low"], "M1 low")
        c = _price(row["close"], "M1 close")
        if not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError("Inconsistent observed M1 OHLC")
        if observed and observed[-1]["end_at"] == end:
            bar = observed[-1]
            bar["high"] = max(bar["high"], h)
            bar["low"] = min(bar["low"], l)
            bar["close"] = c
            bar["observed_m1_count"] += 1
        else:
            observed.append({"end_at": end, "high": h, "low": l,
                             "close": c, "observed_m1_count": 1})
    return observed[-lookback:]


def evaluate_gate_from_observed_m1(signal_at: datetime, m1_rows: list[dict],
                                   closed_trades: list[dict], *,
                                   lookback: int = 4, **frozen_gate_parameters: object) -> dict:
    """Research-only FAC025 evaluation without trusting caller-supplied M15 counts."""
    bars = reconstruct_observed_m15(m1_rows, signal_at, lookback=lookback)
    return evaluate_causal_gate(signal_at, bars, closed_trades,
                                lookback=lookback, **frozen_gate_parameters)
