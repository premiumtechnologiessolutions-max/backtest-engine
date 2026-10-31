"""Synthetic quote-integrity checks; these do not certify trade execution."""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from scripts.liquidity_sweep_signal import M1Bar, detect_liquidity_sweeps


def bar(**changes):
    base = M1Bar(datetime(2026, 1, 5, tzinfo=timezone.utc),
                 100.0, 100.5, 99.5, 100.1, 100.2,
                 100.7, 99.7, 100.3)
    return replace(base, **changes)


def test_complete_ask_ohlc_accepted():
    assert detect_liquidity_sweeps([bar()]) == []


def test_legacy_signal_only_quote_still_accepted():
    assert detect_liquidity_sweeps([bar(ask_high=None, ask_low=None, ask_close=None)]) == []


@pytest.mark.parametrize("changes", [
    {"ask_high": None},
    {"ask_low": None},
    {"ask_close": None},
    {"ask_low": 101.0},
    {"ask_high": 100.4},
    {"ask_close": 99.9},
    {"ask_high": float("nan")},
    {"ask_close": True},
])
def test_partial_or_invalid_ask_ohlc_rejected(changes):
    with pytest.raises(ValueError):
        detect_liquidity_sweeps([bar(**changes)])
