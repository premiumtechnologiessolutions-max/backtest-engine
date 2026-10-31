"""Synthetic execution-input gate regression tests, not backtest parity."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from scripts.liquidity_sweep_signal import M1Bar
from scripts.liquidity_sweep_execution_quotes import require_execution_grade_m1


def bar(minute=0):
    return M1Bar(datetime(2026, 1, 5, tzinfo=timezone.utc) +
                 timedelta(minutes=minute),
                 100., 100.5, 99.5, 100.1, 100.2, 100.7, 99.7, 100.3)


def test_full_ask_contiguous_generator_is_materialized_once():
    rows = require_execution_grade_m1(bar(i) for i in range(6))
    assert len(rows) == 6
    assert rows[-1].time - rows[0].time == timedelta(minutes=5)


def test_legacy_signal_only_quotes_fail_closed():
    with pytest.raises(ValueError, match="full ASK"):
        require_execution_grade_m1([replace(bar(), ask_high=None,
                                             ask_low=None, ask_close=None)])


def test_missing_minute_rejected():
    with pytest.raises(ValueError, match="contiguous"):
        require_execution_grade_m1([bar(0), bar(2)])


def test_duplicate_minute_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        require_execution_grade_m1([bar(0), bar(0)])


def test_invalid_crossed_quote_rejected():
    with pytest.raises(ValueError, match="invalid ASK"):
        require_execution_grade_m1([replace(bar(), ask_low=99.0)])


def test_empty_is_valid_no_op():
    assert require_execution_grade_m1(iter(())) == []
