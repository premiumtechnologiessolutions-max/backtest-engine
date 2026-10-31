"""Regression contracts for chronological exit accounting in the shared gate.

Synthetic only. No historical market data or profitability claims.
"""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_shared_capacity_gate import allow_portfolio_entry


NOW = datetime(2026, 10, 31, 18, tzinfo=timezone.utc)


def gate(rows, **overrides):
    limits = dict(max_daily_loss_usd_per_oz=10.0, max_daily_entries=5,
                  max_open_positions=2)
    limits.update(overrides)
    return allow_portfolio_entry(NOW, rows, **limits)


def test_loss_halt_uses_exit_order_not_entry_order():
    # Earlier entry exits profitably *after* the later entry realizes a loss.
    # Sorting by entry would incorrectly allow another trade.
    rows = [
        (NOW - timedelta(hours=5), NOW - timedelta(hours=1), 15.0),
        (NOW - timedelta(hours=4), NOW - timedelta(hours=2), -10.0),
    ]
    assert gate(rows) is False


def test_prior_day_exit_releases_capacity_for_today():
    rows = [(NOW - timedelta(days=2), NOW - timedelta(days=1), -100.0)]
    assert gate(rows, max_open_positions=1) is True


def test_closed_trade_with_missing_realized_net_is_rejected():
    rows = [(NOW - timedelta(hours=2), NOW - timedelta(hours=1), None)]
    with pytest.raises(ValueError, match="finite realized"):
        gate(rows)


@pytest.mark.parametrize("bad_limit", [0, -1, float("nan"), float("inf"), True])
def test_invalid_daily_loss_limits_fail_closed(bad_limit):
    with pytest.raises(ValueError, match="invalid frozen risk limits"):
        gate([], max_daily_loss_usd_per_oz=bad_limit)


def test_future_entry_is_rejected_even_without_exit():
    with pytest.raises(ValueError, match="past-only"):
        gate([(NOW + timedelta(seconds=1), None, None)])
