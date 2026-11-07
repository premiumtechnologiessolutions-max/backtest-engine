"""Causal source-bar checks for frozen arithmetic training replay.

Synthetic observed M1 marks only. These tests do not prove market edge, original
Gold ZIP parity, or independent out-of-sample performance.
"""
import pandas as pd
import pytest

from scripts.run_arithmetic_dispatch_training import _verify_m1_equity


def _evidence(signal_at: str):
    # 00:03 is missing, but the 00:02 observed candle closes at 00:03.
    # A valid confirmation may therefore occur at a missing OPEN timestamp.
    first = pd.to_datetime([
        "2012-01-01T00:00:00Z",
        "2012-01-01T00:02:00Z",
        "2012-01-01T00:04:00Z",
        "2012-01-01T00:05:00Z",
    ], utc=True)
    later = pd.to_datetime(
        [f"2012-{month:02d}-01T00:00:00Z" for month in range(2, 12)]
        + ["2012-12-31T23:59:00Z"], utc=True)
    stamps = first.append(later)
    realized = [0.0] * 3 + [-0.4] * (len(stamps) - 3)
    marks = pd.DataFrame({
        "at": stamps.astype(str),
        "realized_pnl": realized,
        "floating_pnl": [0.0] * len(stamps),
        "equity": realized,
        "drawdown": [0.0] * 3 + [0.4] * (len(stamps) - 3),
    })
    trades = pd.DataFrame([{
        "signal_at": signal_at,
        "entry_at": "2012-01-01T00:04:00Z",
        "closed_at": "2012-01-01T00:05:00Z",
        "net_pnl": -0.4,
    }])
    summary = {
        "start_utc": stamps[0].isoformat(),
        "end_utc": stamps[-1].isoformat(),
        "max_drawdown_observed_m1": 0.4,
        "last_observed_equity": -0.4,
        "last_observed_realized_pnl": -0.4,
    }
    return trades, marks, summary


def test_signal_confirmed_at_first_missing_minute_after_observed_bar_is_valid():
    # A bar opened at 00:02 and closed at 00:03; next observed fill is 00:04.
    _verify_m1_equity(*_evidence("2012-01-01T00:03:00Z"))


def test_signal_at_observed_entry_open_without_preceding_bar_is_rejected():
    # 00:04 exists, but the 00:03 source candle is missing.
    with pytest.raises(ValueError, match="missing observed signal source bar"):
        _verify_m1_equity(*_evidence("2012-01-01T00:04:00Z"))


def test_signal_before_first_observed_source_bar_is_rejected():
    with pytest.raises(ValueError, match="missing observed signal source bar"):
        _verify_m1_equity(*_evidence("2012-01-01T00:00:00Z"))
