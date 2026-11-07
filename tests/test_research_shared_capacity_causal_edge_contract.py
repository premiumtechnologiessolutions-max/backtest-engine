"""Additional causal safety contracts for shared portfolio capacity."""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_shared_capacity_gate import allow_portfolio_entry


T = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


def gate(trades, **overrides):
    settings = dict(max_daily_loss_usd_per_oz=10.0, max_daily_entries=5,
                    max_open_positions=2)
    settings.update(overrides)
    return allow_portfolio_entry(T, trades, **settings)


def test_exact_loss_threshold_latches_halt():
    assert not gate([(T - timedelta(hours=3), T - timedelta(hours=2), -10.0)])


def test_unobserved_future_exit_cannot_influence_gate():
    with pytest.raises(ValueError, match="exit must be observed"):
        gate([(T - timedelta(hours=1), T + timedelta(minutes=1), 100.0)])


def test_open_position_cannot_claim_realized_profit():
    with pytest.raises(ValueError, match="open trade"):
        gate([(T - timedelta(hours=1), None, 100.0)])


def test_open_positions_consume_shared_capacity():
    rows = [(T - timedelta(hours=2), None, None),
            (T - timedelta(hours=1), None, None)]
    assert not gate(rows)


def test_historical_overcapacity_is_rejected_even_if_positions_closed():
    rows = [(T - timedelta(hours=4), T - timedelta(hours=1), 0.0),
            (T - timedelta(hours=3), T - timedelta(hours=1), 0.0),
            (T - timedelta(hours=2), T - timedelta(hours=1), 0.0)]
    with pytest.raises(ValueError, match="historical trade ledger"):
        gate(rows)
