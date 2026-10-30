"""Fail-closed position chronology tests for canonical arithmetic training replay.

These are synthetic contract tests, not market-data backtests or OOS evidence.
"""
import pandas as pd
import pytest

from scripts.run_arithmetic_dispatch_training import _verify_trade_accounting


def _trade(entry: str, closed: str) -> dict:
    return {
        "strategy": "arithmetic_frozen", "signal_at": entry,
        "entry_at": entry, "closed_at": closed, "side": 1,
        "entry_price": 100.0, "exit_price": 100.0,
        "stop": 99.0, "target": 101.0, "ounces": 1.0,
        "gross_pnl": 0.0, "cost": 0.40, "net_pnl": -0.40,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }


def test_sequential_positions_with_distinct_exit_and_next_entry_minutes_pass():
    trades = pd.DataFrame([
        _trade("2012-01-01T00:01:00Z", "2012-01-01T00:03:00Z"),
        _trade("2012-01-01T02:04:00+02:00", "2012-01-01T02:06:00+02:00"),
    ])
    _verify_trade_accounting(trades)


@pytest.mark.parametrize("second_entry,expected", [
    ("2012-01-01T00:02:00Z", "overlaps"),
    ("2012-01-01T00:03:00Z", "overlaps"),
    ("2012-01-01T00:00:00Z", "chronology"),
])
def test_overlap_same_minute_reentry_or_out_of_order_is_rejected(
        second_entry, expected):
    trades = pd.DataFrame([
        _trade("2012-01-01T00:01:00Z", "2012-01-01T00:03:00Z"),
        _trade(second_entry, "2012-01-01T00:06:00Z"),
    ])
    with pytest.raises(ValueError, match=expected):
        _verify_trade_accounting(trades)


@pytest.mark.parametrize("field", ["signal_at", "entry_at", "closed_at"])
def test_subminute_execution_timestamp_is_rejected(field):
    trade = _trade("2012-01-01T00:01:00Z", "2012-01-01T00:03:00Z")
    trade[field] = {
        "signal_at": "2012-01-01T00:00:30Z",
        "entry_at": "2012-01-01T00:01:30Z",
        "closed_at": "2012-01-01T00:03:30Z",
    }[field]
    with pytest.raises(ValueError, match="non-M1-aligned"):
        _verify_trade_accounting(pd.DataFrame([trade]))


def test_unsorted_closes_rejected_even_when_individual_rows_are_valid():
    trades = pd.DataFrame([
        _trade("2012-01-01T00:01:00Z", "2012-01-01T00:06:00Z"),
        _trade("2012-01-01T00:04:00Z", "2012-01-01T00:05:00Z"),
    ])
    with pytest.raises(ValueError, match="chronology"):
        _verify_trade_accounting(trades)
