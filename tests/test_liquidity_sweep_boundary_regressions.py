"""Synthetic-only boundary tests for preregistered liquidity sweep signals.

These tests do not validate execution, canonical parity, or profitability.
"""
from dataclasses import replace
from datetime import timedelta

from scripts.liquidity_sweep_signal import detect_liquidity_sweeps
from datetime import datetime, timezone
from scripts.liquidity_sweep_signal import M1Bar

T = datetime(2026, 1, 5, tzinfo=timezone.utc)

def fixture():
    bars = [M1Bar(T + timedelta(minutes=i), 100, 100.1, 99.9, 100, 100.02)
            for i in range(1440)]
    bars += [M1Bar(T + timedelta(days=1, minutes=i), 100, 100.1, 99.9, 100, 100.02)
             for i in range(7)]
    bars[1440] = replace(bars[1440], bid_high=100.5)
    return bars


def test_risk_over_twenty_is_rejected():
    bars = fixture()
    # Prior-day high is 100.1; sweep high is 121.0, so stop risk
    # exceeds the frozen $20/oz maximum.
    bars[1440] = replace(bars[1440], bid_high=121.0)
    assert detect_liquidity_sweeps(bars) == []


def test_previous_calendar_day_not_last_observed_day():
    bars = fixture()
    # Move all next-day bars forward by one day. A Monday level cannot
    # be used as Wednesday's previous UTC calendar-day reference.
    shifted = [replace(b, time=b.time + timedelta(days=1)) for b in bars[1440:]]
    assert detect_liquidity_sweeps(bars[:1440] + shifted) == []


def test_next_minute_gap_cannot_be_filled_late():
    bars = fixture()
    # Remove the only eligible next-open minute. A later open must not
    # be used as a synthetic substitute.
    assert detect_liquidity_sweeps(bars[:1445] + bars[1446:]) == []
