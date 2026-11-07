"""Metamorphic tests for prior-session sweep detection (research only).

Shifting every OHLC price by a fixed positive offset must preserve causal
signal timing, direction, and session identity, while shifting level/extreme.
No execution or performance assumptions are made here.
"""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys

path = Path(__file__).resolve().parents[1] / "scripts" / "detect_prior_session_sweeps.py"
spec = importlib.util.spec_from_file_location("sweep_translation_detector", path)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

START = datetime(2026, 10, 27, tzinfo=timezone.utc)


def bar(t, o=100.0, h=101.0, l=99.0, c=100.0):
    return m.Bar(t, o, h, l, c)


def translate(bars, offset):
    return [m.Bar(b.timestamp, b.open + offset, b.high + offset,
                  b.low + offset, b.close + offset) for b in bars]


def test_price_translation_preserves_both_direction_signals():
    prior = [bar(START + timedelta(minutes=i)) for i in range(1440)]
    day = START + timedelta(days=1)
    series = prior + [
        bar(day, h=102, c=101.5),
        bar(day + timedelta(minutes=1), h=104, c=100),
        bar(day + timedelta(minutes=2), l=98, c=98.5),
        bar(day + timedelta(minutes=3), l=96, c=100),
    ]
    original = m.detect_prior_utc_day_sweeps(series)
    assert [s.side for s in original] == ["SELL", "BUY"]
    for offset in (10.0, 1000.0):
        shifted = m.detect_prior_utc_day_sweeps(translate(series, offset))
        assert len(shifted) == len(original)
        for a, b in zip(original, shifted):
            assert (a.confirmed_at, a.side, a.session_date) == (
                b.confirmed_at, b.side, b.session_date)
            assert abs((b.swept_level - a.swept_level) - offset) < 1e-9
            assert abs((b.extreme - a.extreme) - offset) < 1e-9


def test_price_translation_does_not_create_signal_without_reclaim():
    prior = [bar(START + timedelta(minutes=i)) for i in range(1440)]
    day = START + timedelta(days=1)
    series = prior + [bar(day, h=102, c=101.5)]
    assert m.detect_prior_utc_day_sweeps(series) == []
    assert m.detect_prior_utc_day_sweeps(translate(series, 500)) == []
