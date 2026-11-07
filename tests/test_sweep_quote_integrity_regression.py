"""Synthetic fail-closed quote input and execution timing contracts.

These tests do not use real XAUUSD quotes and establish no trading edge.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from scripts.simulate_sweep_bid_ask_research import QuoteBar, simulate_signal

T = datetime(2026, 10, 30, tzinfo=timezone.utc)


def bar(minute=0, *, bid=100.0, spread=0.2):
    return QuoteBar(
        T + timedelta(minutes=minute),
        bid, bid + 0.1, bid - 0.1, bid,
        bid + spread, bid + spread + 0.1, bid + spread - 0.1, bid + spread,
    )


def signal(side="BUY", extreme=98.0):
    return SimpleNamespace(side=side, extreme=extreme, confirmed_at=T)


@pytest.mark.parametrize("field,value", [
    ("bid_open", float("nan")),
    ("ask_high", float("inf")),
    ("bid_close", True),
    ("ask_low", "99.9"),
    ("bid_low", 0),
])
def test_quote_numeric_fields_fail_closed(field, value):
    q = bar()
    data = vars(q).copy()
    data[field] = value
    with pytest.raises(ValueError, match="quote"):
        simulate_signal(signal(), [QuoteBar(**data)])


def test_crossed_bid_ask_rejected():
    q = bar()
    data = vars(q).copy()
    data["ask_open"] = data["bid_open"] - 0.01
    # Keep the ASK OHLC envelope valid so the crossed-market guard is tested.
    data["ask_low"] = min(data["ask_low"], data["ask_open"])
    with pytest.raises(ValueError, match="crossed"):
        simulate_signal(signal(), [QuoteBar(**data)])


def test_duplicate_and_reverse_timestamp_rejected():
    for quotes in ([bar(0), bar(0)], [bar(1), bar(0)]):
        with pytest.raises(ValueError, match="increasing"):
            simulate_signal(signal(), quotes)


def test_no_entry_from_later_available_minute():
    assert simulate_signal(signal(), [bar(-1), bar(1)]) is None


def test_noncontiguous_post_entry_gap_exits_at_adverse_bid_open():
    result = simulate_signal(signal(), [bar(0), bar(2, bid=90)])
    assert result is not None
    assert result.reason == "GAP_OPEN"
    assert result.exit == 90
    assert result.net_per_ounce == pytest.approx(90 - 100.2 - 0.4)
