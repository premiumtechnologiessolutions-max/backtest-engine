"""One-shot iterable regression for the causal liquidity sweep kernel.

Synthetic-only; does not certify market fills, OOS or profitability.
"""
from datetime import datetime, timedelta, timezone

from scripts.liquidity_sweep_signal import M1Bar, detect_liquidity_sweeps


def _sample():
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    previous = [
        M1Bar(start + timedelta(minutes=i), 100.0, 100.1, 99.9, 100.0, 100.02)
        for i in range(1200)
    ]
    today_start = start + timedelta(days=1)
    today = [
        M1Bar(today_start + timedelta(minutes=i), 100.0, 100.1, 99.9, 100.0, 100.02)
        for i in range(6)
    ]
    today[0] = M1Bar(today_start, 100.0, 100.5, 99.9, 100.0, 100.02)
    return previous + today


def test_generator_matches_list_with_nonempty_signal():
    bars = _sample()
    expected = detect_liquidity_sweeps(bars)
    assert len(expected) == 1
    assert detect_liquidity_sweeps(iter(bars)) == expected
    assert detect_liquidity_sweeps((b for b in bars)) == expected


def test_empty_one_shot_iterable_is_safe():
    assert detect_liquidity_sweeps(iter(())) == []
