"""Causal shared-capacity research gate; no broker orders or future observations.

Each trade is (entry_utc, exit_utc_or_None, realized_net_usd_per_oz_or_None).
Only trades entered strictly before the decision may be supplied. An exit at or
after the decision is not observable and must NOT be passed as a known outcome.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware datetimes")
    return value.astimezone(timezone.utc)


def allow_portfolio_entry(
    decision_utc: datetime,
    trades: list[tuple[datetime, datetime | None, float | None]],
    *,
    max_daily_loss_usd_per_oz: float,
    max_daily_entries: int,
    max_open_positions: int = 1,
) -> bool:
    """Enforce shared capacity and entry-based daily cap using past-only trades.

    The daily loss limit uses *realized net* P/L of exits observed today.
    A previously entered trade that remains open consumes shared capacity.
    UTC is a deliberately frozen accounting boundary, not a market session.
    """
    now = _utc(decision_utc)
    if (type(max_daily_entries) is not int or max_daily_entries < 1
            or type(max_open_positions) is not int or max_open_positions < 1
            or isinstance(max_daily_loss_usd_per_oz, bool)
            or not isinstance(max_daily_loss_usd_per_oz, (int, float))
            or not isfinite(max_daily_loss_usd_per_oz)
            or max_daily_loss_usd_per_oz <= 0):
        raise ValueError("invalid frozen risk limits")

    daily_entries = 0
    open_positions = 0
    realized_today = 0.0
    previous_entry = None
    for entry, exit_time, net in trades:
        start = _utc(entry)
        if start >= now or (previous_entry is not None and start < previous_entry):
            raise ValueError("entries must be past-only and chronological")
        previous_entry = start
        if start.date() == now.date():
            daily_entries += 1
        if exit_time is None:
            if net is not None:
                raise ValueError("open trade cannot have realized P/L")
            open_positions += 1
            continue
        end = _utc(exit_time)
        if end < start or end >= now:
            raise ValueError("exit must be observed after entry and before decision")
        if isinstance(net, bool) or not isinstance(net, (int, float)) or not isfinite(net):
            raise ValueError("closed trade requires finite realized net P/L")
        if end.date() == now.date():
            realized_today += net

    return (daily_entries < max_daily_entries
            and open_positions < max_open_positions
            and realized_today > -max_daily_loss_usd_per_oz)
