"""FAC005 frozen ATR/EMA causal no-lookahead and fast-vs-canonical tests."""
import itertools

import numpy as np
import pandas as pd
import pytest

from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.strategy import aggregate_bars
from scripts.batch_donchian_grid import replay_core
from scripts.batch_atr_ema_regime_grid import (
    FAST_EMAS, SLOW_EMAS, REGIME_GATES, STOPS, TARGETS, TOTAL_SPECS,
    h1_relative_atr, ema_cross_arrays, gated_signals, canonical_signals,
)


def continuous_m1(hours=220):
    idx = pd.date_range("2012-01-09T00:00:00Z", periods=hours * 60, freq="min")
    steps = np.arange(len(idx), dtype=float)
    prices = 1650 + 5 * np.sin(steps * 2 * np.pi / (15 * 22)) + .004 * steps / 60
    return pd.DataFrame({
        "o": prices, "h": prices + .30, "l": prices - .30, "c": prices,
    }, index=idx)


def prepared(m1):
    m15 = aggregate_bars(m1, "M15")
    h1 = aggregate_bars(m1, "H1")
    ratio = h1_relative_atr(h1)
    h1_stamps = np.asarray(h1["close_at"].array.asi8 // 1_000_000_000, dtype=np.int64)
    return m15, h1, ratio, h1_stamps


def signals(m1, fast=5, slow=26, gate=.80):
    m15, h1, ratio, stamps = prepared(m1)
    times, sides = ema_cross_arrays(m15, fast, slow)
    return gated_signals(times, sides, stamps, ratio, gate)


def test_frozen_25600_distinct_parameter_specs():
    assert len(FAST_EMAS) == len(SLOW_EMAS) == len(REGIME_GATES) == 4
    assert len(STOPS) == len(TARGETS) == 20
    assert TOTAL_SPECS == 25600
    assert len(set(itertools.product(FAST_EMAS, SLOW_EMAS, REGIME_GATES,
                                     STOPS, TARGETS))) == TOTAL_SPECS


def test_asof_H1_is_never_future_and_never_stale():
    t = np.array([3500, 3600, 7200, 7500, 10800, 14401], dtype=np.int64)
    sides = np.array([1, 1, -1, 1, -1, 1], dtype=np.int8)
    h1 = np.array([3600, 7200, 10800], dtype=np.int64)
    ratio = np.array([.5, 1.5, 2.0])
    kept, side = gated_signals(t, sides, h1, ratio, 1.)
    np.testing.assert_array_equal(kept, [7200, 7500, 10800])
    np.testing.assert_array_equal(side, [-1, 1, -1])


def test_h1_regime_baseline_excludes_current_bar():
    m1 = continuous_m1()
    _, h1, original, _ = prepared(m1)
    changed = h1.copy()
    # Alter ONLY last completed H1; the prior-24 median is unchanged,
    # while the current H1 ATR and therefore the ratio can change.
    changed.iloc[-1, changed.columns.get_loc("h")] += 500
    mutated = h1_relative_atr(changed)
    np.testing.assert_allclose(original[:-1], mutated[:-1], equal_nan=True)
    assert mutated[-1] > original[-1]


def test_missing_H1_candle_disables_regime_until_39_contiguous_transitions():
    m1 = continuous_m1()
    gap = m1.drop(m1.index[100*60:101*60])
    _, h1, ratio, _ = prepared(gap)
    gap_next = np.where(h1.index == m1.index[101*60])[0][0]
    assert np.isnan(ratio[gap_next:gap_next + 39]).all()
    assert np.isfinite(ratio[gap_next + 39])


def test_m15_ema_resets_and_rewarms_after_gap():
    m1 = continuous_m1()
    gap = m1.drop(m1.index[120*60:120*60+15])
    m15 = aggregate_bars(gap, "M15")
    times, sides = ema_cross_arrays(m15, 5, 26)
    after_gap = m1.index[120*60+15].value // 1_000_000_000
    first_valid = after_gap + (26+2)*15*60
    assert all(not after_gap <= t < first_valid for t in times)
    assert len(times) == len(sides)


def test_signal_prefix_unchanged_when_future_bars_are_hidden():
    m1 = continuous_m1()
    full_t, full_s = signals(m1)
    shorter = m1.iloc[:160*60]
    short_t, short_s = signals(shorter)
    assert len(short_t) > 0
    cutoff = shorter.index[-1].value // 1_000_000_000 + 60
    np.testing.assert_array_equal(full_t[full_t <= cutoff], short_t)
    np.testing.assert_array_equal(full_s[:len(short_s)], short_s)


@pytest.mark.parametrize("fast,slow,gate,stop,target", [
    (5, 26, .8, 2., 3.),
    (8, 34, 1., 4., 5.),
    (12, 50, 1.2, 1.5, 2.),
    (16, 72, 1.4, 6., 4.),
])
def test_accelerated_monthly_and_floating_dd_match_canonical(
    fast, slow, gate, stop, target
):
    m1 = continuous_m1()
    t, sides = signals(m1, fast, slow, gate)
    months = (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8)
    monthly, trades, net, fees, dd, _ = replay_core(
        m1.index.asi8 // 1_000_000_000,
        *[m1[k].to_numpy(dtype=float) for k in ("o", "h", "l", "c")],
        months, t, sides, stop, target,
    )
    ref = run_fast(
        m1, canonical_signals(t, sides, stop, target),
        Settings(ounces=1., roundtrip_cost_per_ounce=.40),
    )
    booked = np.bincount(
        pd.to_datetime(ref.trades.closed_at, utc=True).dt.month,
        weights=ref.trades.net_pnl, minlength=13,
    )[1:]
    np.testing.assert_allclose(monthly, booked, atol=1e-7)
    assert trades == len(ref.trades)
    assert net == pytest.approx(ref.trades.net_pnl.sum(), abs=1e-7)
    assert fees == pytest.approx(ref.trades.cost.sum(), abs=1e-7)
    equity = ref.equity.equity
    assert dd == pytest.approx(
        (equity.cummax().clip(lower=0) - equity).clip(lower=0).max(),
        abs=1e-7,
    )


@pytest.mark.parametrize("fast,slow", [(5, 5), (26, 5), (0, 26), (5.5, 26)])
def test_invalid_ema_specs_rejected(fast, slow):
    with pytest.raises(ValueError):
        ema_cross_arrays(aggregate_bars(continuous_m1(4), "M15"), fast, slow)


def test_invalid_regime_gate_rejected():
    with pytest.raises(ValueError):
        gated_signals(np.array([100]), np.array([1]), np.array([0]),
                      np.array([2.]), float("nan"))
