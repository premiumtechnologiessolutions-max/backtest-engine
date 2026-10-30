"""Synthetic-only contract tests; no historical profitability or execution claims."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import pytest
from scripts.liquidity_sweep_signal import M1Bar, detect_liquidity_sweeps

T = datetime(2026, 1, 5, tzinfo=timezone.utc)

def fixture():
    bars = [M1Bar(T + timedelta(minutes=i), 100, 100.1, 99.9, 100, 100.02)
            for i in range(1440)]
    bars += [M1Bar(T + timedelta(days=1, minutes=i), 100, 100.1, 99.9, 100, 100.02)
             for i in range(6)]
    bars[1440] = replace(bars[1440], bid_high=100.5)
    return bars

def test_short_next_open():
    s, = detect_liquidity_sweeps(fixture())
    assert (s.side, s.entry_price, s.stop_price, s.target_price) == (-1, 100, 100.6, 99.4)
    assert s.entry_time == T + timedelta(days=1, minutes=5)

def test_long_ask_entry():
    bars = fixture()
    bars[1440] = replace(bars[1440], bid_high=100.1, bid_low=99.5)
    s, = detect_liquidity_sweeps(bars)
    assert s.side == 1 and s.entry_price == 100.02 and s.stop_price == 99.4

def test_missing_next_minute():
    assert detect_liquidity_sweeps(fixture()[:-1]) == []

def test_partial_previous_day():
    assert detect_liquidity_sweeps(fixture()[250:]) == []

def test_dual_sweep():
    bars = fixture()
    bars[1440] = replace(bars[1440], bid_low=99.5)
    assert detect_liquidity_sweeps(bars) == []

def test_missing_confirmation_minute():
    bars = fixture()
    assert detect_liquidity_sweeps(bars[:1442] + bars[1443:]) == []

def test_nonfinite_rejected():
    bars = fixture()
    bars[0] = replace(bars[0], bid_open=float("nan"))
    with pytest.raises(ValueError):
        detect_liquidity_sweeps(bars)

def test_duplicate_rejected():
    bars = fixture()
    with pytest.raises(ValueError):
        detect_liquidity_sweeps(bars[:1] + bars[:1] + bars[1:])

def test_incomplete_m5_day():
    bars = [b for i, b in enumerate(fixture()) if i >= 1440 or i % 5 != 2]
    assert detect_liquidity_sweeps(bars) == []
