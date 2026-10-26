"""Synthetic reference parity for FAC003 rejection-wick research."""
import numpy as np
import pandas as pd
import pytest
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.strategy import aggregate_bars
from scripts.batch_donchian_grid import replay_core
from scripts.batch_wick_rejection_grid import (
    SPEC, WICK_BODY, MIN_RANGE, STOPS, TARGETS,
    to_native_signals, wick_rejection_signal_arrays,
)


def synthetic(gap):
    t = pd.date_range("2012-01-03", periods=510, freq="min", tz="UTC")
    k = np.arange(len(t))
    v = 1700 + 3.5 * np.sin(k * .2)
    df = pd.DataFrame({
        "o": v, "h": v + 2, "l": v - 2,
        "c": v + .5 * np.cos(k * .15),
    }, index=t)
    if gap:
        df = df.drop(t[210:218])
    return df


def test_parameter_space_size_and_research_id():
    assert len(WICK_BODY) * len(MIN_RANGE) * len(STOPS) * len(TARGETS) == 28800
    assert SPEC["research_id"] == "NRF-FAC-003"


def test_rejection_direction_and_confirmation_are_causal():
    t = pd.date_range("2012-01-03", periods=2, freq="15min", tz="UTC")
    bars = pd.DataFrame({
        "o": [2000., 2000.], "h": [2003., 2004.],
        "l": [1996., 1997.], "c": [2002., 1998.],
        "close_at": t + pd.Timedelta(minutes=15),
    }, index=t)
    stamps, sides = wick_rejection_signal_arrays(
        bars, wick_body=1.0, min_range=1.0
    )
    assert sides.tolist() == [1, -1]
    assert stamps.tolist() == [int(x.timestamp()) for x in bars.close_at]
    incomplete = synthetic(False).iloc[:-1]
    aggregated = aggregate_bars(incomplete, "M15")
    assert (aggregated.close_at <= incomplete.index[-1] + pd.Timedelta(minutes=1)).all()


@pytest.mark.parametrize("gap", [False, True])
@pytest.mark.parametrize("ratio,minrange,stop,target", [
    (0.5, 0.75, 1.0, 1.0),
    (1.0, 2.25, 3.5, 6.0),
    (2.0, 4.5, 6.0, 10.5),
])
def test_fast_replay_matches_original_for_wick_family(gap, ratio, minrange, stop, target):
    m1 = synthetic(gap)
    bars = aggregate_bars(m1, "M15")
    stamps, sides = wick_rejection_signal_arrays(
        bars, wick_body=ratio, min_range=minrange
    )
    monthly, n, net, fees, dd, _ = replay_core(
        m1.index.asi8 // 1000000000,
        *[m1[k].to_numpy(dtype=float) for k in ("o", "h", "l", "c")],
        (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8),
        stamps, sides, float(stop), float(target),
    )
    native = run_fast(
        m1, to_native_signals(stamps, sides, stop, target),
        Settings(ounces=1, roundtrip_cost_per_ounce=.40),
    )
    booked = np.bincount(
        pd.to_datetime(native.trades.closed_at, utc=True).dt.month,
        weights=native.trades.net_pnl.to_numpy(), minlength=13,
    )[1:]
    equity = native.equity.equity
    np.testing.assert_allclose(monthly, booked, atol=1e-9, rtol=0)
    assert n == len(native.trades)
    assert net == pytest.approx(native.trades.net_pnl.sum(), abs=1e-8)
    assert fees == pytest.approx(native.trades.cost.sum(), abs=1e-8)
    assert dd == pytest.approx(
        (equity.cummax().clip(lower=0) - equity).clip(lower=0).max(), abs=1e-8
    )
