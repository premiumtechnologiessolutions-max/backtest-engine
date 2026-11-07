"""Causal UTC M1/M5 liquidity sweep signal research kernel. NO execution/trading."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite

@dataclass(frozen=True)
class M1Bar:
    time: datetime
    bid_open: float
    bid_high: float
    bid_low: float
    bid_close: float
    ask_open: float
    ask_high: float | None = None
    ask_low: float | None = None
    ask_close: float | None = None

@dataclass(frozen=True)
class SweepSignal:
    side: int
    signal_time: datetime
    entry_time: datetime
    entry_price: float
    stop_price: float
    target_price: float
    reference_price: float

def detect_liquidity_sweeps(bars):
    """Signal only; next contiguous M1 open. Does NOT implement position management."""
    # Materialize once: generators must not disappear before the M5 aggregation pass.
    bars = list(bars)
    previous = None
    by_time = {}
    for b in bars:
        if (b.time.tzinfo is None or b.time.utcoffset() != timedelta(0)
                or b.time.second or b.time.microsecond):
            raise ValueError("M1 time must be UTC minute-aligned")
        v = (b.bid_open, b.bid_high, b.bid_low, b.bid_close, b.ask_open)
        if any(isinstance(x, bool) or not isinstance(x, (int, float))
               or not isfinite(x) or x <= 0 for x in v):
            raise ValueError("invalid quote")
        if (b.bid_low > b.bid_high
                or b.bid_low > min(b.bid_open, b.bid_close)
                or b.bid_high < max(b.bid_open, b.bid_close)
                or b.ask_open < b.bid_open):
            raise ValueError("invalid OHLC/spread")
        # Full ASK OHLC is optional for signal-only legacy callers, but any
        # execution-grade quote must provide all three remaining ASK fields.
        ask_tail = (b.ask_high, b.ask_low, b.ask_close)
        if any(x is not None for x in ask_tail):
            if any(x is None for x in ask_tail):
                raise ValueError("partial ASK OHLC is not execution-grade")
            if any(isinstance(x, bool) or not isinstance(x, (int, float))
                   or not isfinite(x) or x <= 0 for x in ask_tail):
                raise ValueError("invalid ASK quote")
            if (b.ask_low > b.ask_high
                    or b.ask_low > min(b.ask_open, b.ask_close)
                    or b.ask_high < max(b.ask_open, b.ask_close)
                    or b.ask_low < b.bid_low or b.ask_high < b.bid_high
                    or b.ask_close < b.bid_close):
                raise ValueError("invalid ASK OHLC/spread")
        if previous is not None and b.time <= previous:
            raise ValueError("unsorted or duplicate M1")
        previous = b.time
        by_time[b.time] = b
    complete = []
    days = {}
    for b in bars:
        if b.time.minute % 5:
            continue
        group = [by_time.get(b.time + timedelta(minutes=k)) for k in range(5)]
        if any(x is None for x in group):
            continue
        hi, lo, close = max(x.bid_high for x in group), min(x.bid_low for x in group), group[-1].bid_close
        complete.append((b.time, hi, lo, close))
        days.setdefault(b.time.date(), []).append((hi, lo))
    levels = {d: (max(x[0] for x in rows), min(x[1] for x in rows))
              for d, rows in days.items() if len(rows) >= 240}
    found = []
    for start, hi, lo, close in complete:
        previous_day = (start - timedelta(days=1)).date()
        if previous_day not in levels:
            continue
        high, low = levels[previous_day]
        short = hi >= high + .20 and close < high
        long = lo <= low - .20 and close > low
        if short == long:
            continue
        entry_time = start + timedelta(minutes=5)
        next_bar = by_time.get(entry_time)
        if next_bar is None:
            continue
        side = 1 if long else -1
        entry = next_bar.ask_open if long else next_bar.bid_open
        stop = lo - .10 if long else hi + .10
        risk = (entry - stop) * side
        if not (0 < risk <= 20):
            continue
        found.append(SweepSignal(side, entry_time, entry_time, entry, stop,
                                 entry + side * risk, low if long else high))
    return found
