"""Reject drift in frozen 20k Donchian countertrend research engine."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from scripts.batch_donchian_grid import LOOKBACKS, STOPS, TARGETS, get_signals, replay_core
from scripts.batch_channel_fade_grid import SPEC
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.strategies_native import donchian_breakout_signals


def fixture(with_gap):
    t = pd.date_range("2012-01-03", periods=285, freq="min", tz="UTC")
    v = 2000 + np.sin(np.arange(285) * 0.15) * 3
    bars = pd.DataFrame({
        "o": v, "h": v + 1, "l": v - 1,
        "c": v + 0.2 * np.cos(np.arange(285) * .2),
    }, index=t)
    return bars.drop(t[45:52]) if with_gap else bars


def test_countertrend_grid_20k_unique():
    assert len(LOOKBACKS) * len(STOPS) * len(TARGETS) == 20000
    assert SPEC["research_id"] == "NRF-FAC-002"


@pytest.mark.parametrize("gap", [False, True])
@pytest.mark.parametrize("lb,stop,target", [
    (5, 1.0, 1.0),
    (15, 6.5, 10.5),
    (24, 13.0, 20.5),
])
def test_inverse_side_parity_against_original_engine(gap, lb, stop, target):
    m1 = fixture(gap)
    times, sides = get_signals(m1, lb)
    projected, n, net, fees, dd, _ = replay_core(
        m1.index.asi8 // 1000000000,
        *[m1[k].to_numpy(dtype=float) for k in ("o", "h", "l", "c")],
        (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8),
        times, -sides, float(stop), float(target),
    )
    native = donchian_breakout_signals(
        m1, timeframe="M15", lookback=lb,
        stop_distance=stop, target_distance=target,
    )
    changed = [
        replace(s, side=-s.side, strategy="donchian_m15_fade")
        for s in native
    ]
    original = run_fast(
        m1, changed, Settings(ounces=1.0, roundtrip_cost_per_ounce=0.40)
    )
    booked = np.bincount(
        pd.to_datetime(original.trades.closed_at, utc=True).dt.month,
        weights=original.trades.net_pnl, minlength=13,
    )[1:]
    equity = original.equity.equity
    np.testing.assert_allclose(projected, booked, atol=1e-9, rtol=0)
    assert n == len(original.trades)
    assert net == pytest.approx(original.trades.net_pnl.sum())
    assert fees == pytest.approx(original.trades.cost.sum())
    assert dd == pytest.approx(
        (equity.cummax().clip(lower=0) - equity).clip(lower=0).max()
    )
