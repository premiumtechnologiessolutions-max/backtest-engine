"""Ambiguous high+low TF sweeps must never survive boundary-close filters.

This guards intrabar unknown ordering (no broker ticks are present).
"""
import pandas as pd
import pytest
from norisk_quant.liquidity_sweep import SweepSettings, liquidity_sweep_signals


def bars(close, high, low, timeframe):
    width = {"M15": 15, "H1": 60}[timeframe]
    start = pd.Timestamp("2024-01-08T12:00:00Z")
    items = []
    for j in range(14):
        o, h, l, c = ((100., 101., 99., 100.) if j != 12
                      else (100., high, low, close))
        for minute in range(width):
            items.append((start + pd.Timedelta(minutes=j * width + minute),
                          o, h, l, c))
    return pd.DataFrame(items, columns=["at", "o", "h", "l", "c"]).set_index("at")


@pytest.mark.parametrize("tf", ["M15", "H1"])
@pytest.mark.parametrize("boundary_close", [99., 100., 101.])
def test_dual_wick_sweep_rejected_even_at_exact_old_channel_boundary(tf, boundary_close):
    source = bars(boundary_close, high=103., low=97., timeframe=tf)
    cfg = SweepSettings(timeframe=tf)
    assert liquidity_sweep_signals(source, settings=cfg) == []


@pytest.mark.parametrize("tf", ["M15", "H1"])
def test_single_low_sweep_boundary_close_remains_supported(tf):
    source = bars(101., high=101., low=98., timeframe=tf)
    cfg = SweepSettings(timeframe=tf)
    trades = liquidity_sweep_signals(source, settings=cfg)
    assert len(trades) == 1
    assert trades[0].side == 1


@pytest.mark.parametrize("tf", ["M15", "H1"])
def test_single_high_sweep_boundary_close_remains_supported(tf):
    source = bars(99., high=102., low=99., timeframe=tf)
    cfg = SweepSettings(timeframe=tf)
    trades = liquidity_sweep_signals(source, settings=cfg)
    assert len(trades) == 1
    assert trades[0].side == -1
