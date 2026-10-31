"""Causal temporal-boundary regression tests for the shared portfolio gate.

Synthetic contracts only; no market data or trading performance claims.
"""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_shared_capacity_gate import allow_portfolio_entry


NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


def check(trades, **kwargs):
    limits = dict(max_daily_loss_usd_per_oz=10.0, max_daily_entries=5,
                  max_open_positions=2)
    limits.update(kwargs)
    return allow_portfolio_entry(NOW, trades, **limits)


def test_daily_loss_halt_stays_latched_after_recovery():
    trades = [
        (NOW - timedelta(hours=5), NOW - timedelta(hours=4), -10.0),
        (NOW - timedelta(hours=3), NOW - timedelta(hours=2), 15.0),
    ]
    assert check(trades) is False


def test_prior_day_realized_loss_does_not_trigger_current_utc_day_halt():
    yesterday = NOW.replace(hour=0, minute=0) - timedelta(minutes=1)
    trades = [(yesterday - timedelta(hours=1), yesterday, -100.0)]
    assert check(trades) is True


def test_today_entry_limit_includes_closed_trades():
    trades = [
        (NOW - timedelta(hours=4), NOW - timedelta(hours=3), 1.0),
        (NOW - timedelta(hours=2), NOW - timedelta(hours=1), 1.0),
    ]
    assert check(trades, max_daily_entries=2) is False


def test_exit_at_decision_time_is_not_observed():
    with pytest.raises(ValueError, match="exit must be observed"):
        check([(NOW - timedelta(minutes=1), NOW, -1.0)])


def test_timezone_offset_represents_same_utc_instant():
    offset = timezone(timedelta(hours=3))
    entry = (NOW - timedelta(hours=2)).astimezone(offset)
    exit_time = (NOW - timedelta(hours=1)).astimezone(offset)
    assert check([(entry, exit_time, 1.0)]) is True


def test_reject_naive_decision_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        allow_portfolio_entry(NOW.replace(tzinfo=None), [],
                              max_daily_loss_usd_per_oz=10.0,
                              max_daily_entries=5)


def test_historical_capacity_released_at_exact_exit_instant():
    first = (NOW - timedelta(hours=3), NOW - timedelta(hours=2), 0.0)
    second = (NOW - timedelta(hours=2), NOW - timedelta(hours=1), 0.0)
    assert check([first, second], max_open_positions=1) is True
