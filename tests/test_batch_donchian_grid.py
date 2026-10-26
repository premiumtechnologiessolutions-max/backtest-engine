"""Synthetic parity and hypothesis-size contract for high-volume batch replay."""
import numpy as np
import pandas as pd
import pytest

from scripts.batch_donchian_grid import (
    LOOKBACKS, STOPS, TARGETS, replay_core, get_signals,
)
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.strategies_native import donchian_breakout_signals


def fixture(gap=False):
    times = pd.date_range("2012-01-03", periods=270, freq="min", tz="UTC")
    baseline = 2000 + 3 * np.sin(np.arange(270) * .15)
    bars = pd.DataFrame({
        "o": baseline,
        "h": baseline + 1,
        "l": baseline - 1,
        "c": baseline + np.cos(np.arange(270) * .2) * .2,
    }, index=times)
    if gap:
        bars = bars.drop(times[53:58]).drop(times[160:167])
    return bars


def test_exactly_twenty_thousand_unique_parameter_specs():
    assert len(LOOKBACKS) * len(STOPS) * len(TARGETS) == 20000
    assert len({
        (lb, sl, tp)
        for lb in LOOKBACKS for sl in STOPS for tp in TARGETS
    }) == 20000


@pytest.mark.parametrize("gap", [False, True])
@pytest.mark.parametrize("lb,stop,target", [
    (5, 1., 1.), (10, 3.5, 7.), (24, 13., 20.5),
])
def test_bulk_engine_matches_real_fast_engine_months_and_floating_drawdown(
    gap, lb, stop, target,
):
    m1 = fixture(gap)
    times, sides = get_signals(m1, lb)
    monthly, trades, net, fees, maxdd, _ = replay_core(
        m1.index.asi8 // 1_000_000_000,
        *[m1[k].to_numpy(dtype=float) for k in ("o", "h", "l", "c")],
        (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8),
        times, sides, float(stop), float(target),
    )
    native = donchian_breakout_signals(
        m1, timeframe="M15", lookback=lb,
        stop_distance=stop, target_distance=target,
    )
    expected = run_fast(
        m1, native, Settings(ounces=1, roundtrip_cost_per_ounce=.40)
    )
    by_month = np.bincount(
        pd.to_datetime(expected.trades.closed_at, utc=True).dt.month,
        weights=expected.trades.net_pnl, minlength=13,
    )[1:]
    equity = expected.equity.equity
    ref_drawdown = (
        equity.cummax().clip(lower=0) - equity
    ).clip(lower=0).max()
    np.testing.assert_allclose(monthly, by_month, atol=1e-9, rtol=0)
    assert trades == len(expected.trades)
    assert fees == pytest.approx(expected.trades.cost.sum(), abs=1e-8)
    assert net == pytest.approx(expected.trades.net_pnl.sum(), abs=1e-8)
    assert maxdd == pytest.approx(ref_drawdown, abs=1e-8)
