"""UTC-equivalent exit timestamps must be one atomic risk event.

Synthetic contract only; no market data, backtest, or trading claim.
"""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_shared_capacity_gate import allow_portfolio_entry


NOW = datetime(2026, 11, 1, 18, tzinfo=timezone.utc)
UTC = timezone.utc
PLUS_TWO = timezone(timedelta(hours=2))


def gate(rows):
    return allow_portfolio_entry(
        NOW, rows,
        max_daily_loss_usd_per_oz=10.0,
        max_daily_entries=5,
        max_open_positions=2,
    )


@pytest.mark.parametrize("nets,expected", [
    ((-12.0, 5.0), True),
    ((5.0, -12.0), True),
    ((-15.0, 5.0), False),
    ((5.0, -15.0), False),
])
def test_equal_instants_with_different_offsets_are_atomic(nets, expected):
    same_utc = NOW - timedelta(hours=1)
    same_plus_two = same_utc.astimezone(PLUS_TWO)
    rows = [
        (NOW - timedelta(hours=4), same_utc, nets[0]),
        (NOW - timedelta(hours=3), same_plus_two, nets[1]),
    ]
    assert gate(rows) is expected


def test_distinct_utc_instants_do_not_batch_even_if_wall_clock_matches():
    # The same displayed clock hour with different offsets is NOT the same instant.
    early = datetime(2026, 11, 1, 14, tzinfo=UTC)
    late = datetime(2026, 11, 1, 14, tzinfo=PLUS_TWO)
    # late is 12:00 UTC, so it precedes early; loss at 12:00 must stay sticky.
    rows = [
        (datetime(2026, 11, 1, 10, tzinfo=UTC), early, 5.0),
        (datetime(2026, 11, 1, 11, tzinfo=UTC), late, -12.0),
    ]
    assert gate(rows) is False
