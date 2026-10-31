from datetime import datetime, timezone, timedelta
import pytest
from scripts.research_causal_daily_halt import allow_entry

UTC = timezone.utc

def t(day, hour):
    return datetime(2026, 10, day, hour, tzinfo=UTC)

def test_daily_loss_and_capacity():
    exits = [(t(30, 20), -20.0), (t(31, 9), -3.0), (t(31, 10), -2.0)]
    assert not allow_entry(t(31, 11), exits, max_daily_loss_usd_per_oz=5, max_daily_trades=3)
    assert allow_entry(t(31, 11), exits, max_daily_loss_usd_per_oz=6, max_daily_trades=3)
    assert not allow_entry(t(31, 11), exits, max_daily_loss_usd_per_oz=6, max_daily_trades=2)

def test_utc_day_boundary_and_offset():
    local = timezone(timedelta(hours=2))
    assert allow_entry(datetime(2026, 11, 1, 3, tzinfo=local),
        [(t(31, 21), -9.0)], max_daily_loss_usd_per_oz=5, max_daily_trades=2)
    assert allow_entry(t(31, 23), [(t(30, 23), -9.0)],
        max_daily_loss_usd_per_oz=5, max_daily_trades=2)

@pytest.mark.parametrize("exits", [
    [(t(31, 11), -1.0)], [(t(31, 12), -1.0)],
    [(t(31, 10), -1.0), (t(31, 9), -1.0)],
    [(t(31, 10), float("nan"))],
    [(datetime(2026, 10, 31, 10), -1.0)],
])
def test_rejects_noncausal_or_corrupt_ledger(exits):
    with pytest.raises(ValueError):
        allow_entry(t(31, 11), exits, max_daily_loss_usd_per_oz=5, max_daily_trades=2)

def test_rejects_invalid_limits():
    with pytest.raises(ValueError):
        allow_entry(t(31, 11), [], max_daily_loss_usd_per_oz=5, max_daily_trades=True)


def test_daily_halt_stable_cancellation_preserves_small_loss():
    # Naive accumulation loses -6 between opposite 1e16 outcomes.
    exits = [(t(31, 8), 1e16), (t(31, 9), -6.0), (t(31, 10), -1e16)]
    assert not allow_entry(t(31, 11), exits, max_daily_loss_usd_per_oz=5,
                           max_daily_trades=4)


def test_daily_halt_aggregate_overflow_fails_closed():
    exits = [(t(31, 8), 1e308), (t(31, 9), 1e308)]
    with pytest.raises(ValueError, match="overflow"):
        allow_entry(t(31, 11), exits, max_daily_loss_usd_per_oz=5,
                    max_daily_trades=4)
