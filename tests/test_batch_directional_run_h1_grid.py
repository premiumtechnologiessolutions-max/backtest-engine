"""Public synthetic-only FAC011 causality, DST and M1 execution tests."""
import numpy as np
import pandas as pd
import pytest

from scripts.batch_directional_run_h1_grid import (
    RUN_LENGTHS, MOVE_THRESHOLDS, TOTAL, SPEC,
    directional_run_signals, causal_filters, filtered_signals,
)
from scripts.batch_donchian_grid import replay_core


def _bars():
    idx = pd.date_range("2026-01-05", periods=42, freq="15min", tz="UTC")
    close = np.empty(len(idx))
    close[0] = 100.
    for i in range(1, len(idx)):
        close[i] = close[i-1] + (1 if i % 2 else -1)
    close[-4] = close[-5]
    close[-3] = close[-4] - 2
    close[-2] = close[-3] + 2
    close[-1] = close[-2] + 2
    op = np.r_[close[0], close[:-1]]
    high = np.maximum(op, close) + 1
    low = np.minimum(op, close) - 1
    return pd.DataFrame({
        "o": op, "h": high, "l": low, "c": close,
        "close_at": idx + pd.Timedelta(minutes=15),
    }, index=idx)


def test_frozen_grid_size_and_identity():
    assert TOTAL == 19200
    assert len(RUN_LENGTHS)*len(MOVE_THRESHOLDS)*2*2*3*10*10 == TOTAL
    assert SPEC["preregistration_commit"] == "4dc11184bc6118aab8e97450bc0c0c884cd23d85"


def test_exact_run_and_no_lookahead():
    bars = _bars()
    times, sides = directional_run_signals(bars, 2, 1.)
    assert len(times) == 1 and sides.tolist() == [1]
    assert times[0] == int(bars.close_at.iloc[-1].timestamp())
    earlier, _ = directional_run_signals(bars.iloc[:-1], 2, 1.)
    assert len(earlier) == 0


def test_missing_m15_breaks_run():
    bars = _bars()
    bars = bars.drop(bars.index[-2])
    times, sides = directional_run_signals(bars, 2, 1.)
    assert len(times) == 0 and len(sides) == 0


def test_large_move_threshold_rejects_small_run():
    times, _ = directional_run_signals(_bars(), 2, 3.)
    assert len(times) == 0


def test_reject_unfrozen_inputs():
    with pytest.raises(ValueError):
        directional_run_signals(_bars(), 1, 1.)
    with pytest.raises(ValueError):
        directional_run_signals(_bars(), 2, 1.1)


def test_dst_london_and_ny_are_local_not_fixed_utc():
    at = pd.to_datetime([
        "2026-01-15T08:15:00Z", "2026-07-15T07:15:00Z",
        "2026-01-15T14:30:00Z", "2026-07-15T13:30:00Z",
    ], utc=True)
    bars = pd.DataFrame({"close_at": at})
    h1 = pd.DataFrame({"close_at": pd.to_datetime([], utc=True), "h": [], "l": []})
    _, regime, masks = causal_filters(bars, h1)
    assert regime.tolist() == [0, 0, 0, 0]
    assert masks["LONDON_LOCAL_08_12"].tolist() == [True, True, False, False]
    assert masks["NY_LOCAL_0930_1330"].tolist() == [False, False, True, True]


def test_regime_filter_fails_closed_and_reverses_only_side():
    times = np.array([60, 120, 180], dtype=np.int64)
    sides = np.array([1, -1, 1], dtype=np.int8)
    regimes = np.array([1, 2, 0], dtype=np.int8)
    masks = {
        "ALL": np.array([True, True, True]),
        "LONDON_LOCAL_08_12": np.array([True, False, True]),
        "NY_LOCAL_0930_1330": np.array([False, True, True]),
    }
    t, s = filtered_signals(times, sides, times, regimes, masks,
                            "FADE", "QUIET", "ALL")
    assert t.tolist() == [60] and s.tolist() == [-1]
    t, s = filtered_signals(times, sides, times, regimes, masks,
                            "FOLLOW", "HOT", "ALL")
    assert t.tolist() == [120] and s.tolist() == [-1]


def test_stop_first_and_exact_single_fee():
    stamps = np.array([0, 60, 120], np.int64)
    op = np.array([100., 100., 100.])
    hi = np.array([100.5, 101.5, 100.])
    lo = np.array([99.5, 98.5, 100.])
    cl = np.array([100., 100., 100.])
    monthly, n, net, fee, dd, expired = replay_core(
        stamps, op, hi, lo, cl, np.zeros(3, np.int8),
        np.array([0], np.int64), np.array([1], np.int8), 1., 1.)
    assert n == 1 and abs(net + 1.4) < 1e-8 and abs(fee - .4) < 1e-8
    assert abs(monthly[0] + 1.4) < 1e-8 and expired == 0


def test_gap_through_stop_uses_adverse_observed_open():
    stamps = np.array([0, 60, 180], np.int64)
    op = np.array([100., 100., 95.])
    hi = np.array([100.5, 100.5, 95.5])
    lo = np.array([99.5, 99.5, 94.5])
    cl = np.array([100., 100., 95.])
    monthly, n, net, fee, dd, expired = replay_core(
        stamps, op, hi, lo, cl, np.zeros(3, np.int8),
        np.array([0], np.int64), np.array([1], np.int8), 1., 2.)
    assert n == 1 and abs(net + 5.4) < 1e-8 and abs(fee - .4) < 1e-8
