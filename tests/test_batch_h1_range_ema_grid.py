"""FAC005B gap-aware H1 realized-range / M15 EMA frozen regression checks."""
import itertools

import numpy as np
import pandas as pd
import pytest

from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.strategy import aggregate_bars
from scripts.batch_donchian_grid import replay_core
from scripts.batch_h1_range_ema_grid import (
    FAST_EMAS, SLOW_EMAS, REGIME_GATES, STOPS, TARGETS, TOTAL_SPECS,
    h1_range_relative, ema_cross_arrays, gated_signals, canonical_signals,
)


def continuous_m1(hours=220):
    idx = pd.date_range("2012-01-09T00:00:00Z", periods=hours*60, freq="min")
    steps = np.arange(len(idx), dtype=float)
    p = 1650 + 5*np.sin(steps*2*np.pi/(15*22)) + .004*steps/60
    return pd.DataFrame({"o": p, "h": p+.3, "l": p-.3, "c": p}, index=idx)


def prepared(m1):
    m15 = aggregate_bars(m1, "M15")
    h1 = aggregate_bars(m1, "H1")
    ratio = h1_range_relative(h1)
    h1_times = np.asarray(h1["close_at"].array.asi8 // 1_000_000_000,
                          dtype=np.int64)
    return m15, h1, ratio, h1_times


def signals(m1, fast=5, slow=26, gate=.8):
    m15, h1, ratio, h1_t = prepared(m1)
    times, sides = ema_cross_arrays(m15, fast, slow)
    return gated_signals(times, sides, h1_t, ratio, gate)


def test_25600_distinct_specs():
    assert TOTAL_SPECS == 25600
    assert len(set(itertools.product(FAST_EMAS, SLOW_EMAS, REGIME_GATES,
                                     STOPS, TARGETS))) == 25600


def test_previous_24_h1_median_excludes_current_bar():
    m15, h1, ratio, _ = prepared(continuous_m1())
    assert np.isfinite(ratio).sum() > 150
    mutated = h1.copy()
    mutated.iloc[-1, mutated.columns.get_loc("h")] += 500
    newer = h1_range_relative(mutated)
    np.testing.assert_allclose(ratio[:-1], newer[:-1], equal_nan=True)
    assert newer[-1] > ratio[-1]


def test_daily_H1_gap_is_not_filled_but_followup_has_valid_regime():
    m1 = continuous_m1()
    m1 = m1.drop(m1.index[100*60:101*60])
    _, h1, ratio, _ = prepared(m1)
    assert not (h1.index == pd.Timestamp("2012-01-13T04:00:00Z")).any()
    after_gap = np.where(h1.index == m1.index[100*60])[0] if False else np.flatnonzero(
        h1.index > pd.Timestamp("2012-01-13T04:00:00Z")
    )
    assert len(after_gap)
    assert np.isfinite(ratio[after_gap[0]:after_gap[0]+8]).any()


def test_expired_24_h1_baseline_rejected_without_interpolation():
    index = pd.date_range("2012-01-01T00:00:00Z", periods=35, freq="8h")
    h1 = pd.DataFrame({"h": 10., "l": 5.,
                       "close_at": index + pd.Timedelta(hours=1)}, index=index)
    ratio = h1_range_relative(h1)
    assert np.isnan(ratio).all()


def test_future_cannot_change_prior_cross_or_h1_gate():
    m1 = continuous_m1()
    full_t, full_s = signals(m1)
    partial = m1.iloc[:160*60]
    short_t, short_s = signals(partial)
    assert len(short_t) > 0
    cutoff = partial.index[-1].value // 1_000_000_000 + 60
    np.testing.assert_array_equal(full_t[full_t <= cutoff], short_t)
    np.testing.assert_array_equal(full_s[:len(short_s)], short_s)


@pytest.mark.parametrize("fast,slow,gate,stop,target", [
    (5,26,.8,2.,3.), (8,34,1.,4.,5.),
    (12,50,1.2,1.5,2.), (16,72,1.4,6.,4.),
])
def test_filled_trades_and_monthly_dd_match_reference(fast,slow,gate,stop,target):
    m1 = continuous_m1()
    t, sides = signals(m1, fast, slow, gate)
    monthly, trades, net, fees, dd, _ = replay_core(
        m1.index.asi8 // 1_000_000_000,
        *[m1[k].to_numpy(dtype=float) for k in ("o", "h", "l", "c")],
        (m1.index.month.to_numpy(dtype=np.int16)-1).astype(np.int8),
        t, sides, stop, target,
    )
    ref = run_fast(m1, canonical_signals(t,sides,stop,target),
                   Settings(ounces=1.,roundtrip_cost_per_ounce=.4))
    booked = np.bincount(
        pd.to_datetime(ref.trades.closed_at,utc=True).dt.month,
        weights=ref.trades.net_pnl,minlength=13,
    )[1:]
    np.testing.assert_allclose(monthly,booked,atol=1e-7)
    assert trades == len(ref.trades)
    assert net == pytest.approx(ref.trades.net_pnl.sum(),abs=1e-7)
    assert fees == pytest.approx(ref.trades.cost.sum(),abs=1e-7)
    equity = ref.equity.equity
    assert dd == pytest.approx(
        (equity.cummax().clip(lower=0)-equity).clip(lower=0).max(),abs=1e-7,
    )


def test_asof_regime_no_future_or_stale():
    times = np.array([3500,7200,7500,14401],dtype=np.int64)
    sides = np.array([1,-1,1,-1],dtype=np.int8)
    h1 = np.array([3600,7200,10800],dtype=np.int64)
    ratio = np.array([.5,1.5,2.0])
    t,s = gated_signals(times,sides,h1,ratio,1.)
    np.testing.assert_array_equal(t,[7200,7500])
    np.testing.assert_array_equal(s,[-1,1])
