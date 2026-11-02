"""Causality and data-integrity tests for the research-only sweep detector."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import pytest

p = Path(__file__).resolve().parents[1] / "scripts" / "detect_prior_session_sweeps.py"
spec = importlib.util.spec_from_file_location("sweep_detector", p)
m = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = m
spec.loader.exec_module(m)

T = datetime(2026, 10, 29, tzinfo=timezone.utc)
def bar(t, o=100.0, h=101.0, l=99.0, c=100.0):
    return m.Bar(t, o, h, l, c)
def prior():
    return [bar(T + timedelta(minutes=i)) for i in range(1440)]
def current(*xs):
    start = T + timedelta(days=1)
    return [bar(start + timedelta(minutes=i), *v) for i,v in enumerate(xs)]

def test_sweep_then_next_bar_reclaim_only():
    xs = prior() + current((100, 102, 99, 101.5), (101.5, 102, 99, 100))
    assert m.detect_prior_utc_day_sweeps(xs) == [
        m.SweepSignal(T + timedelta(days=1, minutes=2), "SELL", 101, 102, "2026-10-30")
    ]

def test_no_same_bar_reclaim_and_no_future_leak():
    xs = prior() + current((100, 102, 99, 100))
    assert m.detect_prior_utc_day_sweeps(xs) == []
    xs += current((100, 102, 99, 100), (100, 101, 99, 100))[1:]
    assert len(m.detect_prior_utc_day_sweeps(xs)) == 1

def test_incomplete_prior_day_never_used():
    assert m.detect_prior_utc_day_sweeps(prior()[:-1] +
        current((100, 102, 99, 101.5), (101.5, 102, 99, 100))) == []

def test_gap_resets_pending():
    xs = prior()
    start = T + timedelta(days=1)
    xs += [bar(start, 100, 102, 99, 101.5), bar(start + timedelta(minutes=2))]
    assert m.detect_prior_utc_day_sweeps(xs) == []

def test_low_sweep_buy():
    xs = prior() + current((100, 101, 98, 98.5), (98.5, 101, 98, 100))
    out = m.detect_prior_utc_day_sweeps(xs)
    assert len(out) == 1 and out[0].side == "BUY"

def test_duplicate_and_bad_envelope_rejected():
    xs = prior()
    with pytest.raises(ValueError):
        m.detect_prior_utc_day_sweeps(xs + [xs[-1]])
    with pytest.raises(ValueError):
        m.detect_prior_utc_day_sweeps([bar(T, 100, 99, 98, 100)])

def test_reject_nonpositive_threshold():
    with pytest.raises(ValueError):
        m.detect_prior_utc_day_sweeps([], min_sweep_usd=0)

def test_reclaim_bar_extends_sell_extreme_without_future_leak():
    xs = prior() + current((100, 102, 99, 101.5), (101.5, 104, 99, 100))
    result = m.detect_prior_utc_day_sweeps(xs)
    assert len(result) == 1
    assert result[0].extreme == 104
    assert result[0].confirmed_at == T + timedelta(days=1, minutes=2)


def test_reclaim_bar_extends_buy_extreme_without_future_leak():
    xs = prior() + current((100, 101, 98, 98.5), (98.5, 101, 96, 100))
    result = m.detect_prior_utc_day_sweeps(xs)
    assert len(result) == 1
    assert result[0].extreme == 96
    assert result[0].confirmed_at == T + timedelta(days=1, minutes=2)
