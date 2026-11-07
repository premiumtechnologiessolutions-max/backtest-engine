"""Synthetic RSI-recoss signal and canonical bulk replay regression checks."""
import numpy as np
import pandas as pd
import pytest

from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.strategy import aggregate_bars
from scripts.batch_donchian_grid import replay_core
from scripts.batch_rsi_recross_grid import (
    PERIODS, THRESHOLDS, STOPS, TARGETS, TOTAL_SPECS,
    rsi_recross_arrays, canonical_signals,
)


def minute_fixture():
    index = pd.date_range("2012-01-09T00:00:00Z", periods=100 * 15, freq="min")
    phase = np.arange(len(index)) * (2 * np.pi / (15 * 22))
    values = 2000 + 8 * np.sin(phase)
    return pd.DataFrame({
        "o": values, "h": values + 0.35,
        "l": values - 0.35, "c": values,
    }, index=index)


def test_grid_is_25600_unique_specs_per_year():
    assert len(PERIODS) == 8 and len(THRESHOLDS) == 8
    assert len(STOPS) == 20 and len(TARGETS) == 20
    assert TOTAL_SPECS == 25600
    assert len(set((p, t, s, x)
                   for p in PERIODS for t in THRESHOLDS
                   for s in STOPS for x in TARGETS)) == TOTAL_SPECS


def test_close_confirmation_both_sides_and_no_future_knowledge():
    bars = aggregate_bars(minute_fixture(), "M15")
    stamps, sides = rsi_recross_arrays(bars, 5, 40)
    assert len(stamps) > 1
    assert set(sides.tolist()) == {-1, 1}
    available = set((bars["close_at"].array.asi8 // 1_000_000_000).tolist())
    assert set(stamps.tolist()).issubset(available)
    first_half = bars.iloc[:60]
    before_t, before_s = rsi_recross_arrays(first_half, 5, 40)
    np.testing.assert_array_equal(stamps[stamps <= before_t[-1]], before_t)
    np.testing.assert_array_equal(sides[:len(before_s)], before_s)


def test_completely_missing_M15_bar_disables_immediate_gap_recross():
    bars = aggregate_bars(minute_fixture(), "M15")
    gap = bars.drop(bars.index[65])
    timestamps, sides = rsi_recross_arrays(gap, 5, 40)
    excluded_start = bars.index[65].value // 1_000_000_000
    excluded_end = bars.index[72].value // 1_000_000_000
    assert all(not excluded_start <= t < excluded_end for t in timestamps)
    assert len(timestamps) == len(sides)


@pytest.mark.parametrize("period,threshold,stop,target", [
    (5, 40, 2., 2.5), (7, 35, 4., 5.),
    (11, 30, 1.5, 3.), (14, 25, 6., 4.),
])
def test_rsi_bulk_matches_canonical_market_replay(period, threshold, stop, target):
    m1 = minute_fixture()
    bars = aggregate_bars(m1, "M15")
    stamps, side = rsi_recross_arrays(bars, period, threshold)
    monthly, trades, net, fee, dd, _ = replay_core(
        m1.index.asi8 // 1_000_000_000,
        *[m1[c].to_numpy(dtype=float) for c in ("o", "h", "l", "c")],
        (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8),
        stamps, side, stop, target,
    )
    original = run_fast(m1, canonical_signals(stamps, side, stop, target),
                        Settings(ounces=1.0, roundtrip_cost_per_ounce=.4))
    expected_month = np.bincount(
        pd.to_datetime(original.trades.closed_at, utc=True).dt.month,
        weights=original.trades.net_pnl, minlength=13,
    )[1:]
    np.testing.assert_allclose(monthly, expected_month, atol=1e-7)
    assert trades == len(original.trades)
    assert net == pytest.approx(original.trades.net_pnl.sum(), abs=1e-7)
    assert fee == pytest.approx(original.trades.cost.sum(), abs=1e-7)
    equity = original.equity.equity
    assert dd == pytest.approx((equity.cummax().clip(lower=0) - equity).clip(lower=0).max(), abs=1e-7)


@pytest.mark.parametrize("period,threshold", [(0, 20), (5, 50), (5, 0), (5.5, 20)])
def test_invalid_rsi_spec_rejected(period, threshold):
    with pytest.raises(ValueError):
        rsi_recross_arrays(aggregate_bars(minute_fixture(), "M15"), period, threshold)
