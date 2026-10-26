"""Synthetic no-lookahead tests for frozen compression-breakout rules."""
import pandas as pd
import pytest

from norisk_quant.compression_breakout import (
    CompressionSettings, compression_breakout_signals,
)


def synthetic_compression():
    first = pd.Timestamp("2012-01-09T00:00:00Z")
    rows = []
    for i in range(63):
        high, low, close = (2003.0, 1997.0, 2000.0) if i < 52 else (2000.2, 1999.8, 2000.0)
        if i == 60:
            high, low, close = 2000.85, 1999.9, 2000.7
        for m in range(15):
            rows.append((first + pd.Timedelta(minutes=15 * i + m),
                         2000.0, high, low, close))
    return pd.DataFrame(rows, columns=["at", "o", "h", "l", "c"]).set_index("at")


def test_compression_uses_only_previous_channel_and_confirms_at_close():
    src = synthetic_compression()
    result = compression_breakout_signals(src)
    assert len(result) == 1
    one = result[0]
    assert one.side == 1
    assert one.confirmed_at == pd.Timestamp("2012-01-09T15:15:00Z")
    assert one.stop_distance == pytest.approx(1.0)
    assert one.target_distance == pytest.approx(1.8)


def test_cannot_signal_before_current_candle_fully_closes():
    src = synthetic_compression()
    assert compression_breakout_signals(src.loc[: "2012-01-09T15:14:00Z"]) == []


def test_missing_minute_in_lookback_rejects_breakout():
    src = synthetic_compression()
    src = src.drop(pd.Timestamp("2012-01-09T14:00:00Z"))
    assert compression_breakout_signals(src) == []


def test_future_market_mutation_never_changes_old_signal():
    src = synthetic_compression()
    before = compression_breakout_signals(src)
    modified = src.copy()
    modified.loc[modified.index >= pd.Timestamp("2012-01-09T15:15:00Z"), ["o", "h", "l", "c"]] = [
        2000, 2060, 1900, 2020
    ]
    assert compression_breakout_signals(modified) == before


@pytest.mark.parametrize("bad", [
    {"timeframe": "H4"}, {"range_bars": True}, {"range_bars": 2},
    {"baseline_bars": 20}, {"contraction_ratio": 1},
    {"breakout_buffer_usd": 0}, {"reward_risk": float("nan")},
    {"min_stop_usd": 5, "max_stop_usd": 4},
])
def test_reject_invalid_hypothesis_parameters(bad):
    with pytest.raises(ValueError):
        CompressionSettings(**bad)
