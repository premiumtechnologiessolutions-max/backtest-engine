"""Fail-closed, strategy-independent validation of execution-grade M1 quotes.

This is an input gate, not a fill simulator or evidence of backtest parity.
No trading strategy or signal detection is invoked.
"""
from datetime import timedelta
from math import isfinite


def _positive_number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and isfinite(value) and value > 0)


def require_execution_grade_m1(bars):
    """Materialize once and validate contiguous UTC minute-aligned BID/ASK OHLC.

    An empty input is a valid no-op. The returned list preserves the source
    records and never manufactures missing ASK quotes or timestamps.
    """
    rows = list(bars)
    previous_time = None
    for row in rows:
        t = row.time
        if (t.tzinfo is None or t.utcoffset() != timedelta(0)
                or t.second or t.microsecond):
            raise ValueError("M1 time must be UTC minute-aligned")
        if previous_time is not None:
            if t <= previous_time:
                raise ValueError("unsorted or duplicate M1")
            if t - previous_time != timedelta(minutes=1):
                raise ValueError("execution requires contiguous M1 quotes")
        previous_time = t

        bid = (row.bid_open, row.bid_high, row.bid_low, row.bid_close)
        if not all(_positive_number(x) for x in bid):
            raise ValueError("invalid quote")
        if (row.bid_low > row.bid_high
                or row.bid_low > min(row.bid_open, row.bid_close)
                or row.bid_high < max(row.bid_open, row.bid_close)):
            raise ValueError("invalid OHLC/spread")

        ask_tail = (row.ask_high, row.ask_low, row.ask_close)
        if any(x is None for x in ask_tail):
            raise ValueError("execution requires full ASK OHLC")
        ask = (row.ask_open, *ask_tail)
        if not all(_positive_number(x) for x in ask):
            raise ValueError("invalid ASK quote")
        if (row.ask_low > row.ask_high
                or row.ask_low > min(row.ask_open, row.ask_close)
                or row.ask_high < max(row.ask_open, row.ask_close)
                or row.ask_open < row.bid_open
                or row.ask_high < row.bid_high
                or row.ask_low < row.bid_low
                or row.ask_close < row.bid_close):
            raise ValueError("invalid ASK OHLC/spread")
    return rows
