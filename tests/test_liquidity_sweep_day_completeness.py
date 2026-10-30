"""Synthetic UTC-day completeness boundary contracts for liquidity-sweep signals.

These tests validate signal construction only, not fills, profitability, or OOS.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from scripts.liquidity_sweep_signal import M1Bar, detect_liquidity_sweeps

DAY = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _bars(previous_complete_groups: int):
    # Exactly N contiguous completed M5 groups, followed by a new UTC day.
    prior = [
        M1Bar(DAY + timedelta(minutes=i), 100.0, 100.1, 99.9, 100.0, 100.02)
        for i in range(previous_complete_groups * 5)
    ]
    today = [
        M1Bar(DAY + timedelta(days=1, minutes=i), 100.0, 100.1, 99.9, 100.0, 100.02)
        for i in range(6)
    ]
    today[0] = replace(today[0], bid_high=100.5)
    return prior + today


def test_239_complete_m5_previous_day_is_not_eligible():
    assert detect_liquidity_sweeps(_bars(239)) == []


def test_240_complete_m5_previous_day_is_eligible():
    signal, = detect_liquidity_sweeps(_bars(240))
    assert signal.side == -1
    assert signal.reference_price == 100.1
    assert signal.entry_time == DAY + timedelta(days=1, minutes=5)


def test_missing_one_minute_reduces_240_complete_groups_to_239():
    bars = _bars(240)
    missing = DAY + timedelta(minutes=2)
    assert detect_liquidity_sweeps([bar for bar in bars if bar.time != missing]) == []


def test_current_day_extreme_cannot_change_previous_day_reference():
    bars = _bars(240)
    bars[-1] = replace(bars[-1], bid_high=10000.0)
    signal, = detect_liquidity_sweeps(bars)
    assert signal.reference_price == 100.1
