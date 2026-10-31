from datetime import datetime, timedelta, timezone
import pytest
from scripts.research_shared_capacity_gate import allow_portfolio_entry

UTC = timezone.utc
def t(day, hour):
    return datetime(2026, 10, day, hour, tzinfo=UTC)

def gate(now, trades, **kwargs):
    return allow_portfolio_entry(now, trades, max_daily_loss_usd_per_oz=5,
                                 max_daily_entries=2, **kwargs)

def test_open_trade_consumes_shared_capacity_even_without_exit():
    assert not gate(t(31, 12), [(t(30, 20), None, None)])
    assert gate(t(31, 12), [(t(30, 20), t(31, 10), 1.0)])

def test_daily_limit_counts_entries_not_exits():
    trades = [(t(31, 8), t(31, 9), 1.0), (t(31, 10), t(31, 11), 1.0)]
    assert not gate(t(31, 12), trades)
    assert gate(t(31, 12), [(t(30, 22), t(31, 9), 1.0)])

def test_realized_loss_uses_exit_day_and_net():
    assert not gate(t(31, 12), [(t(30, 20), t(31, 10), -5.0)])
    assert gate(t(31, 12), [(t(30, 20), t(30, 23), -9.0)])

def test_offset_timezone_normalized():
    local = timezone(timedelta(hours=2))
    assert not gate(datetime(2026, 11, 1, 1, tzinfo=local),
                    [(t(31, 20), None, None)])

@pytest.mark.parametrize("trades", [
    [(t(31, 12), None, None)],
    [(t(31, 9), t(31, 12), 1.0)],
    [(t(31, 9), t(31, 8), 1.0)],
    [(t(31, 9), None, 1.0)],
    [(t(31, 9), t(31, 10), None)],
    [(t(31, 9), t(31, 10), float("nan"))],
    [(t(31, 10), None, None), (t(31, 9), None, None)],
    [(datetime(2026, 10, 31, 9), None, None)],
])
def test_rejects_noncausal_or_corrupt_trade_ledger(trades):
    with pytest.raises(ValueError):
        gate(t(31, 12), trades)

def test_invalid_limits_fail_closed():
    with pytest.raises(ValueError):
        allow_portfolio_entry(t(31, 12), [], max_daily_loss_usd_per_oz=5,
                              max_daily_entries=True)
    with pytest.raises(ValueError):
        gate(t(31, 12), [], max_open_positions=0)


def test_rejects_historical_over_capacity_even_when_all_positions_closed():
    trades = [(t(31, 8), t(31, 10), 1.0),
              (t(31, 9), t(31, 11), 1.0)]
    with pytest.raises(ValueError, match="exceeds shared capacity"):
        gate(t(31, 12), trades)
    assert gate(t(31, 12), trades, max_open_positions=2) is False  # daily entries cap


def test_exit_at_next_entry_is_not_overlap():
    trades = [(t(31, 8), t(31, 9), 1.0),
              (t(31, 9), t(31, 10), 1.0)]
    assert not gate(t(31, 12), trades)  # two entries, not capacity corruption


def test_two_concurrent_trades_with_two_slots_are_valid():
    trades = [(t(30, 8), t(31, 10), 1.0),
              (t(30, 9), t(31, 11), 1.0)]
    assert gate(t(31, 12), trades, max_open_positions=2)


def test_daily_realized_overflow_fails_closed():
    # Each realized fill is finite, but their sum is not representable.
    trades = [(t(31, 8), t(31, 9), 1e308),
              (t(31, 10), t(31, 11), 1e308)]
    with pytest.raises(ValueError, match="overflow"):
        gate(t(31, 12), trades)


def test_daily_realized_cancellation_is_stable():
    # An ordinary running sum loses the small loss between large offsets.
    trades = [(t(31, 8), t(31, 9), 1e16),
              (t(31, 10), t(31, 11), -6.0),
              (t(31, 12), t(31, 13), -1e16)]
    assert not allow_portfolio_entry(t(31, 14), trades,
                                     max_daily_loss_usd_per_oz=5,
                                     max_daily_entries=4)
