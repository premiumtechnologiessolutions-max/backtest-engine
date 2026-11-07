"""Regression tests: a daily realized-loss halt remains latched after recovery."""
from datetime import datetime, timezone, timedelta

from scripts.research_shared_capacity_gate import allow_portfolio_entry


def _at(hour: int, minute: int = 0):
    return datetime(2026, 10, 31, hour, minute, tzinfo=timezone.utc)


def test_daily_halt_stays_latched_after_later_profit():
    trades = [
        (_at(8), _at(9), -11.0),
        (_at(10), _at(11), 12.0),
    ]
    assert not allow_portfolio_entry(
        _at(12), trades, max_daily_loss_usd_per_oz=10.0,
        max_daily_entries=10,
    )


def test_out_of_order_entries_still_use_exit_chronology():
    # Earlier entry exits after a later entry; loss breach occurs at 10:00.
    trades = [
        (_at(7), _at(11), 15.0),
        (_at(8), _at(10), -12.0),
    ]
    assert not allow_portfolio_entry(
        _at(12), trades, max_daily_loss_usd_per_oz=10.0,
        max_daily_entries=10, max_open_positions=2,
    )


def test_halt_resets_at_next_utc_day():
    trades = [(_at(8), _at(9), -11.0)]
    assert allow_portfolio_entry(
        _at(12) + timedelta(days=1), trades,
        max_daily_loss_usd_per_oz=10.0, max_daily_entries=10,
    )


def test_no_breach_allows_entry():
    trades = [
        (_at(8), _at(9), -9.0),
        (_at(10), _at(11), 3.0),
    ]
    assert allow_portfolio_entry(
        _at(12), trades, max_daily_loss_usd_per_oz=10.0,
        max_daily_entries=10,
    )
