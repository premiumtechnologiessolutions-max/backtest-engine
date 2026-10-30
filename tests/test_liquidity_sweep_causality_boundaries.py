"""Additional causal and boundary regression tests for the signal-only kernel.

These are synthetic contracts, not evidence of profitable execution.
"""
from dataclasses import replace
from datetime import timedelta

import pytest

from scripts.liquidity_sweep_signal import detect_liquidity_sweeps
from tests.test_liquidity_sweep_signal import T, fixture


def test_future_bars_cannot_rewrite_already_emitted_signal():
    bars = fixture()
    first = detect_liquidity_sweeps(bars)
    assert len(first) == 1
    # Future day price extremes may not change an earlier reference level.
    future = [replace(b, time=b.time + timedelta(days=2),
                      bid_high=1000.0, bid_low=1.0)
              for b in bars[:10]]
    assert detect_liquidity_sweeps(bars + future)[:1] == first


def test_reference_is_strictly_previous_calendar_day():
    bars = fixture()
    # A gap of a whole day must not silently use the last available session.
    shifted = [replace(b, time=b.time + timedelta(days=1))
               for b in bars[1440:]]
    assert detect_liquidity_sweeps(bars[:1440] + shifted) == []


def test_exact_sweep_threshold_qualifies():
    bars = fixture()
    bars[1440] = replace(bars[1440], bid_high=100.3)
    assert len(detect_liquidity_sweeps(bars)) == 1


def test_below_sweep_threshold_rejected():
    bars = fixture()
    bars[1440] = replace(bars[1440], bid_high=100.299)
    assert detect_liquidity_sweeps(bars) == []


def test_no_same_candle_entry_without_next_minute():
    bars = fixture()[:-1]
    assert detect_liquidity_sweeps(bars) == []


def test_negative_spread_rejected():
    bars = fixture()
    bars[0] = replace(bars[0], ask_open=99.0)
    with pytest.raises(ValueError, match="OHLC/spread"):
        detect_liquidity_sweeps(bars)
