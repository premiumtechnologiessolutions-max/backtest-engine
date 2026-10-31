"""Fail-closed quote eligibility for execution research; no trading or fills.

The signal generator deliberately accepts legacy BID OHLC + ASK open records.
Execution research MUST NOT silently reuse that permissive contract.
"""
from datetime import timedelta
from math import isfinite

from scripts.liquidity_sweep_signal import detect_liquidity_sweeps


def require_execution_grade_m1(bars):
    """Return validated, contiguous full BID/ASK M1 bars.

    Materialize once for generator safety. This gate validates input integrity
    only; it does not certify the downstream execution engine.
    """
    rows = list(bars)
    # Reuse the signal kernel's existing strict UTC and quote integrity checks.
    detect_liquidity_sweeps(rows)
    for row in rows:
        if any(getattr(row, name) is None for name in
               ("ask_high", "ask_low", "ask_close")):
            raise ValueError("execution requires full ASK OHLC")
        if row.time != rows[0].time and row.time - previous.time != timedelta(minutes=1):
            raise ValueError("execution requires contiguous M1 quotes")
        previous = row
    return rows
