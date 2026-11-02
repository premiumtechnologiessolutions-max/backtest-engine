"""Synthetic execution prefix-causality regression tests (no market-data claims)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from scripts.simulate_sweep_bid_ask_research import QuoteBar, simulate_signal

T = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)


def quote(minute, bid_open=100.0, bid_high=None, bid_low=None, spread=0.2):
    high = bid_open + 0.1 if bid_high is None else bid_high
    low = bid_open - 0.1 if bid_low is None else bid_low
    return QuoteBar(
        T + timedelta(minutes=minute),
        bid_open, high, low, bid_open,
        bid_open + spread, high + spread, low + spread, bid_open + spread,
    )


@pytest.mark.parametrize("side,extreme,hit", [
    ("BUY", 99.0, quote(1, bid_open=100, bid_high=102, bid_low=98)),
    ("SELL", 101.0, quote(1, bid_open=100, bid_high=102, bid_low=98)),
])
def test_completed_fill_is_invariant_to_appended_future_quotes(side, extreme, hit):
    signal = SimpleNamespace(side=side, extreme=extreme, confirmed_at=T)
    prefix = [quote(0), hit]
    original = simulate_signal(signal, prefix)
    assert original is not None
    assert original.reason == "STOP"  # Both levels touched: conservative stop-first.
    extended = prefix + [quote(2, 500), quote(3, 500)]
    assert simulate_signal(signal, extended) == original


@pytest.mark.parametrize("side,extreme,expected", [
    ("BUY", 99.0, "STOP"),
    ("SELL", 101.0, "STOP"),
])
def test_same_bar_dual_touch_is_stop_first(side, extreme, expected):
    signal = SimpleNamespace(side=side, extreme=extreme, confirmed_at=T)
    fill = simulate_signal(signal, [quote(0, bid_high=103, bid_low=97)])
    assert fill is not None
    assert fill.reason == expected
    assert fill.net_per_ounce == pytest.approx(fill.gross_per_ounce - 0.40)
