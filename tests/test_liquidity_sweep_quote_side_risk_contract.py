"""Synthetic-only boundary checks for the liquidity sweep signal kernel.

These tests do not certify executable exits, market data, or profitability.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from scripts.liquidity_sweep_signal import M1Bar, detect_liquidity_sweeps


START = datetime(2026, 1, 5, tzinfo=timezone.utc)


def _bars():
    previous = [
        M1Bar(START + timedelta(minutes=i), 100.0, 100.1, 99.9, 100.0, 100.02)
        for i in range(1200)
    ]
    next_day = START + timedelta(days=1)
    current = [
        M1Bar(next_day + timedelta(minutes=i), 100.0, 100.1, 99.9, 100.0, 100.02)
        for i in range(6)
    ]
    current[0] = replace(current[0], bid_high=100.5)
    return previous + current


def test_short_entry_uses_bid_not_ask():
    bars = _bars()
    bars[-1] = replace(bars[-1], ask_open=101.0)
    signals = detect_liquidity_sweeps(bars)
    assert len(signals) == 1
    assert signals[0].side == -1
    assert signals[0].entry_price == 100.0


def test_long_entry_uses_ask_and_risk_is_measured_from_ask():
    bars = _bars()
    bars[-6] = replace(bars[-6], bid_high=100.1, bid_low=99.5)
    bars[-1] = replace(bars[-1], ask_open=101.0)
    signals = detect_liquidity_sweeps(bars)
    assert len(signals) == 1
    assert signals[0].side == 1
    assert signals[0].entry_price == 101.0
    assert abs(signals[0].target_price - 102.6) < 1e-9


def test_long_risk_above_twenty_is_rejected():
    bars = _bars()
    bars[-6] = replace(bars[-6], bid_high=100.1, bid_low=99.5)
    bars[-1] = replace(bars[-1], ask_open=120.0)
    assert detect_liquidity_sweeps(bars) == []


def test_short_risk_above_twenty_is_rejected():
    bars = _bars()
    bars[-1] = replace(bars[-1], bid_open=70.0, bid_high=100.1, bid_low=69.9, bid_close=70.0, ask_open=70.02)
    assert detect_liquidity_sweeps(bars) == []
