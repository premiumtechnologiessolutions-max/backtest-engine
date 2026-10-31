"""Reject impossible BID candle ranges before M5 liquidity aggregation."""
from datetime import datetime, timezone
import pytest
from scripts.liquidity_sweep_signal import M1Bar, detect_liquidity_sweeps


@pytest.mark.parametrize("low,high", [(101.0, 100.0), (101.0, 100.5)])
def test_inverted_bid_range_fails_closed(low, high):
    # Open and close alone do not reveal the inverted high/low bounds.
    bar = M1Bar(datetime(2026, 1, 5, tzinfo=timezone.utc),
                100.5, high, low, 100.5, 100.6)
    with pytest.raises(ValueError, match="invalid OHLC/spread"):
        detect_liquidity_sweeps([bar])


def test_valid_bid_range_remains_accepted():
    bar = M1Bar(datetime(2026, 1, 5, tzinfo=timezone.utc),
                100.5, 101.0, 100.0, 100.5, 100.6)
    assert detect_liquidity_sweeps(iter([bar])) == []
