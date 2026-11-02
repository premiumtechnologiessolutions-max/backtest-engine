"""Research-only conservative BID/ASK execution for confirmed sweep signals.

Not wired to production backtests. OHLC cannot establish intraminute order:
if stop and target both touch, stop wins. Entries use the first available
contiguous M1 OPEN at/after confirmation; never the confirmation bar.
Net USD per ounce uses exactly 0.40 all-in cost, with no extra spread fee
because BID/ASK execution already accounts for spread.
"""
from dataclasses import dataclass
from datetime import timedelta
import math

COST_PER_OUNCE = 0.40

@dataclass(frozen=True)
class QuoteBar:
    timestamp: object  # UTC-aware minute-open datetime
    bid_open: float
    bid_high: float
    bid_low: float
    bid_close: float
    ask_open: float
    ask_high: float
    ask_low: float
    ask_close: float

@dataclass(frozen=True)
class Fill:
    side: str
    entry_time: object
    exit_time: object
    entry: float
    exit: float
    stop: float
    target: float
    reason: str
    gross_per_ounce: float
    net_per_ounce: float

def simulate_signal(signal, quotes, *, stop_buffer=0.10, reward_r=1.0, max_hold_minutes=90):
    """Return Fill or None if no immediately contiguous executable entry.

    One position only is the caller's responsibility. Quotes must be sorted,
    minute-contiguous and valid; any gap after entry exits at the first
    available next quote OPEN (gap slippage is reflected in BID/ASK).
    """
    from datetime import datetime
    if signal.side not in ("BUY", "SELL"):
        raise ValueError("unsupported side")
    if not isinstance(signal.confirmed_at, datetime) or signal.confirmed_at.tzinfo is None:
        raise ValueError("confirmation must be timezone aware")
    if isinstance(stop_buffer, bool) or not isinstance(stop_buffer, (int, float)) or not math.isfinite(stop_buffer) or stop_buffer <= 0:
        raise ValueError("invalid stop buffer")
    if isinstance(reward_r, bool) or not isinstance(reward_r, (int, float)) or not math.isfinite(reward_r) or reward_r <= 0:
        raise ValueError("invalid reward multiple")
    if type(max_hold_minutes) is not int or max_hold_minutes < 1:
        raise ValueError("invalid hold period")
    qs = list(quotes)
    previous = None
    for q in qs:
        if not isinstance(q.timestamp, datetime) or q.timestamp.tzinfo is None or q.timestamp.utcoffset() != timedelta(0) or q.timestamp.second or q.timestamp.microsecond:
            raise ValueError("quotes require UTC minute timestamps")
        if previous is not None and q.timestamp <= previous:
            raise ValueError("quotes must be strictly increasing")
        previous = q.timestamp
        bid = (q.bid_open, q.bid_high, q.bid_low, q.bid_close)
        ask = (q.ask_open, q.ask_high, q.ask_low, q.ask_close)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in bid + ask):
            raise ValueError("invalid quote prices")
        if q.bid_low > min(bid) or q.bid_high < max(bid) or q.ask_low > min(ask) or q.ask_high < max(ask):
            raise ValueError("invalid quote envelope")
        if any(a < b for a, b in zip(ask, bid)):
            raise ValueError("crossed BID/ASK quote")
    start = next((i for i, q in enumerate(qs) if q.timestamp >= signal.confirmed_at), None)
    if start is None or qs[start].timestamp != signal.confirmed_at:
        return None
    first = qs[start]
    buy = signal.side == "BUY"
    entry = first.ask_open if buy else first.bid_open
    stop = signal.extreme - stop_buffer if buy else signal.extreme + stop_buffer
    risk = entry - stop if buy else stop - entry
    if risk <= 0 or not math.isfinite(risk):
        return None
    target = entry + risk * reward_r if buy else entry - risk * reward_r
    def finish(q, px, reason):
        gross = px - entry if buy else entry - px
        return Fill(signal.side, first.timestamp, q.timestamp, entry, px, stop, target,
                    reason, gross, gross - COST_PER_OUNCE)
    for i in range(start, len(qs)):
        q = qs[i]
        if i > start and q.timestamp - qs[i-1].timestamp != timedelta(minutes=1):
            return finish(q, q.bid_open if buy else q.ask_open, "GAP_OPEN")
        if i - start >= max_hold_minutes:
            return finish(q, q.bid_open if buy else q.ask_open, "TIME_OPEN")
        if buy:
            if q.bid_open <= stop:
                return finish(q, q.bid_open, "STOP_GAP")
            if q.bid_open >= target:
                return finish(q, q.bid_open, "TARGET_GAP")
            if q.bid_low <= stop:
                return finish(q, stop, "STOP")
            if q.bid_high >= target:
                return finish(q, target, "TARGET")
        else:
            if q.ask_open >= stop:
                return finish(q, q.ask_open, "STOP_GAP")
            if q.ask_open <= target:
                return finish(q, q.ask_open, "TARGET_GAP")
            if q.ask_high >= stop:
                return finish(q, stop, "STOP")
            if q.ask_low <= target:
                return finish(q, target, "TARGET")
    return None
