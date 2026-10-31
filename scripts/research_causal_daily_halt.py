"""Causal, research-only session risk gate; never reads future outcomes.

The caller supplies only exits observed strictly before decision_utc.
This module does not execute orders or certify a strategy.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite


def allow_entry(decision_utc: datetime, observed_exits: list[tuple[datetime, float]],
                *, max_daily_loss_usd_per_oz: float, max_daily_trades: int) -> bool:
    """Fail closed on invalid inputs; UTC day resets, no prospective leakage."""
    if decision_utc.tzinfo is None or decision_utc.utcoffset() is None:
        raise ValueError("decision must be timezone-aware")
    if (type(max_daily_trades) is not int or max_daily_trades < 1
            or not isfinite(max_daily_loss_usd_per_oz)
            or max_daily_loss_usd_per_oz <= 0):
        raise ValueError("invalid frozen risk limits")
    now = decision_utc.astimezone(timezone.utc)
    net = 0.0
    trades = 0
    previous = None
    for exit_time, pnl in observed_exits:
        if exit_time.tzinfo is None or exit_time.utcoffset() is None:
            raise ValueError("exit must be timezone-aware")
        stamp = exit_time.astimezone(timezone.utc)
        if stamp >= now:
            raise ValueError("future or simultaneous exit supplied")
        if previous is not None and stamp < previous:
            raise ValueError("exit ledger must be chronological")
        previous = stamp
        if not isfinite(pnl):
            raise ValueError("nonfinite realized P/L")
        if stamp.date() == now.date():
            net += pnl
            trades += 1
    return trades < max_daily_trades and net > -max_daily_loss_usd_per_oz
