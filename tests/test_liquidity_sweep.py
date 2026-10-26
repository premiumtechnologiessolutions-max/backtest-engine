"""Synthetic causality and ambiguity tests for frozen liquidity sweep rules."""
import pandas as pd
import pytest

from norisk_quant.liquidity_sweep import SweepSettings, liquidity_sweep_signals


def fixture_m15():
    start = pd.Timestamp("2024-01-08T12:00:00Z")
    rows = []
    for i in range(14):
        o, h, l, c = (100.0, 101.0, 99.0, 100.0)
        if i == 12:
            o, h, l, c = (100.0, 100.8, 98.0, 99.5)
        for minute in range(15):
            rows.append((start + pd.Timedelta(minutes=15 * i + minute), o, h, l, c))
    return pd.DataFrame(rows, columns=["at", "o", "h", "l", "c"]).set_index("at")


def test_confirm_only_at_completed_m15_close():
    bars = fixture_m15()
    signals = liquidity_sweep_signals(bars)
    assert len(signals) == 1
    assert signals[0].side == 1
    assert signals[0].confirmed_at == pd.Timestamp("2024-01-08T15:15:00Z")
    assert signals[0].stop_distance == pytest.approx(1.6)
    assert signals[0].target_distance == pytest.approx(2.4)


def test_incomplete_sweep_bar_does_not_generate_signal():
    data = fixture_m15()
    assert not liquidity_sweep_signals(data.drop(data.index[180]))


def test_future_bar_mutation_cannot_change_existing_signal():
    data = fixture_m15()
    prior = liquidity_sweep_signals(data)[0]
    data = data.copy()
    data.loc[data.index[-15:], ["o", "h", "l", "c"]] = [100, 108, 99, 100]
    assert liquidity_sweep_signals(data)[0] == prior


def test_ambiguous_bidirectional_sweep_rejected():
    data = fixture_m15().copy()
    data.loc[data.index[180:195], ["h", "l"]] = [103.0, 97.0]
    assert not liquidity_sweep_signals(data)


@pytest.mark.parametrize("kwargs", [
    {"lookback_bars": True}, {"lookback_bars": 1},
    {"reward_risk": float("nan")}, {"penetration_usd": 0},
    {"min_stop_usd": 5, "max_stop_usd": 4}, {"timeframe": "H4"},
])
def test_invalid_sweep_spec(kwargs):
    with pytest.raises(ValueError):
        SweepSettings(**kwargs)
