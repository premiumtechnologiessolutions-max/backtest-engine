"""Prefix invariance: adding future completed bars cannot rewrite past sweep signals.

Research-only contract tests. No raw XAUUSD data or performance claims.
"""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys

path = Path(__file__).resolve().parents[1] / "scripts" / "detect_prior_session_sweeps.py"
spec = importlib.util.spec_from_file_location("prefix_sweep_detector", path)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

START = datetime(2026, 10, 27, tzinfo=timezone.utc)


def b(ts, high=101.0, low=99.0, close=100.0):
    return module.Bar(ts, 100.0, high, low, close)


def test_prefix_invariance_across_reclaims_and_future_days():
    prior = [b(START + timedelta(minutes=i)) for i in range(1440)]
    day = START + timedelta(days=1)
    current = [
        b(day, high=102.0, close=101.5),
        b(day + timedelta(minutes=1), high=104.0, close=100.0),
        b(day + timedelta(minutes=2), low=98.0, close=98.5),
        b(day + timedelta(minutes=3), low=97.0, close=100.0),
    ]
    full = prior + current
    expected = module.detect_prior_utc_day_sweeps(full)
    assert [s.side for s in expected] == ["SELL", "BUY"]
    for end in range(len(prior), len(full) + 1):
        prefix = full[:end]
        cutoff = prefix[-1].timestamp + timedelta(minutes=1)
        assert module.detect_prior_utc_day_sweeps(prefix) == [
            signal for signal in expected if signal.confirmed_at <= cutoff
        ]
    # A new day and a discontinuity must not rewrite the existing signal ledger.
    future = [b(day + timedelta(days=1)), b(day + timedelta(days=1, minutes=3))]
    assert module.detect_prior_utc_day_sweeps(full + future) == expected


def test_no_signal_before_confirming_bar_close():
    prior = [b(START + timedelta(minutes=i)) for i in range(1440)]
    day = START + timedelta(days=1)
    sweep = b(day, high=102.0, close=101.5)
    reclaim = b(day + timedelta(minutes=1), high=103.0, close=100.0)
    assert module.detect_prior_utc_day_sweeps(prior + [sweep]) == []
    result = module.detect_prior_utc_day_sweeps(prior + [sweep, reclaim])
    assert len(result) == 1
    assert result[0].confirmed_at == day + timedelta(minutes=2)
