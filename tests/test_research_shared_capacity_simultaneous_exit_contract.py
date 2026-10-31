"""Simultaneous exits are one observable accounting event, not row-order events.

Synthetic regression; no market-data or profitability assertion.
"""
from datetime import datetime, timedelta, timezone

from scripts.research_shared_capacity_gate import allow_portfolio_entry


NOW = datetime(2026, 11, 1, 18, tzinfo=timezone.utc)


def check(profits):
    t = NOW - timedelta(hours=1)
    rows = [
        (NOW - timedelta(hours=4 - i), t, pnl)
        for i, pnl in enumerate(profits)
    ]
    return allow_portfolio_entry(
        NOW, rows, max_daily_loss_usd_per_oz=10.0,
        max_daily_entries=5, max_open_positions=2,
    )


def test_same_instant_net_above_halt_is_order_invariant():
    assert check([-12.0, 5.0]) is True
    assert check([5.0, -12.0]) is True


def test_same_instant_net_at_halt_is_order_invariant():
    assert check([-15.0, 5.0]) is False
    assert check([5.0, -15.0]) is False


def test_distinct_exit_instants_remain_sticky():
    early = NOW - timedelta(hours=2)
    late = NOW - timedelta(hours=1)
    rows = [
        (NOW - timedelta(hours=4), late, 5.0),
        (NOW - timedelta(hours=3), early, -12.0),
    ]
    assert allow_portfolio_entry(
        NOW, rows, max_daily_loss_usd_per_oz=10.0,
        max_daily_entries=5, max_open_positions=2,
    ) is False
