"""Causal synthetic M1 research; no evidence of trading performance."""
from __future__ import annotations

import pandas as pd
import pytest

from norisk_quant.liquidity_sweep_m1 import sweep_reclaim_m1_signals
from norisk_quant.model import Settings
from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast


def frame(rows, *, start="2024-01-03T00:00:00Z", times=None):
    idx = pd.to_datetime(times, utc=True) if times is not None else pd.date_range(start, periods=len(rows), freq="min", tz="UTC")
    return pd.DataFrame(rows, columns=["o", "h", "l", "c"], index=idx, dtype=float)


def base():
    return [[100, 101, 99, 100] for _ in range(3)]


def run_sweep(x, **params):
    return sweep_reclaim_m1_signals(x, lookback=3, min_excess_usd=.2,
                                    reclaim_usd=.1, stop_buffer_usd=.2,
                                    reward_risk=2., max_stop_usd=9., **params)


def test_bullish_sweep_only_after_confirmation_close():
    x = frame(base() + [[100, 100.2, 98.2, 99.4], [99.4, 100.2, 99.2, 100.]])
    sig = run_sweep(x)
    assert len(sig) == 1
    assert sig[0].side == 1
    assert sig[0].confirmed_at == pd.Timestamp("2024-01-03T00:04:00Z")
    assert sig[0].stop_distance == pytest.approx(1.4)
    assert sig[0].target_distance == pytest.approx(2.8)
    assert run_sweep(x.iloc[:3]) == []
    assert len(run_sweep(x.iloc[:4])) == 1


def test_bearish_sweep():
    x = frame(base() + [[100, 102.0, 99.8, 100.2]])
    sig = run_sweep(x)
    assert len(sig) == 1
    assert sig[0].side == -1
    assert sig[0].stop_distance == pytest.approx(2.0)


def test_dual_sweep_unknown_order_rejected():
    x = frame(base() + [[100, 102.0, 98.0, 100.2]])
    assert run_sweep(x) == []


def test_close_outside_prior_range_rejected():
    x = frame(base() + [[100, 101.5, 99.0, 101.2]])
    assert run_sweep(x) == []


def test_not_reclaimed_rejected():
    x = frame(base() + [[100, 100.1, 98.5, 98.9]])
    assert run_sweep(x) == []


def test_cross_quote_gap_detection_window_rejected():
    dates = ["2024-01-03T00:00:00Z", "2024-01-03T00:01:00Z",
             "2024-01-03T00:03:00Z", "2024-01-03T00:04:00Z"]
    x = frame(base() + [[100, 100.2, 98.2, 99.4]], times=dates)
    assert run_sweep(x) == []


def test_future_candle_mutation_cannot_change_prior_signal():
    x = frame(base() + [[100, 100.2, 98.2, 99.4], [100, 100, 99, 99.5]])
    first = run_sweep(x)[0]
    x.iloc[-1] = [100, 180, 90, 110]
    assert run_sweep(x)[0] == first


def test_no_entry_before_confirmed_close_and_fixed_fee_reference_fast_parity():
    x = frame(base() + [[100, 100.2, 98.2, 99.4], [99.4, 100.1, 99.0, 100.0], [100, 104, 99.8, 103]])
    sig = run_sweep(x)
    assert len(sig) == 1
    ref = run(x, sig, Settings(roundtrip_cost_per_ounce=.40))
    fast = run_fast(x, sig, Settings(roundtrip_cost_per_ounce=.40))
    assert len(ref.trades) == 1
    assert len(fast.trades) == 1
    assert ref.trades.iloc[0]["entry_at"] == x.index[4]
    assert ref.trades.iloc[0]["cost"] == pytest.approx(.40)
    assert ref.trades.iloc[0]["net_pnl"] == pytest.approx(fast.trades.iloc[0]["net_pnl"])


@pytest.mark.parametrize("kwargs", [
    {"lookback": True}, {"lookback": 3.5}, {"lookback": 1},
    {"min_excess_usd": 0}, {"min_excess_usd": -1},
    {"reclaim_usd": float("nan")}, {"reward_risk": float("inf")},
    {"stop_buffer_usd": True}, {"max_stop_usd": 0},
])
def test_reject_invalid_parameters(kwargs):
    params = dict(lookback=3, min_excess_usd=.2, reclaim_usd=.1,
                  stop_buffer_usd=.2, reward_risk=2., max_stop_usd=9.)
    params.update(kwargs)
    with pytest.raises(ValueError):
        sweep_reclaim_m1_signals(frame(base()), **params)


@pytest.mark.parametrize("rows", [
    [[100, 101, 99, 100], [100, 101, 99, 100], [100, 101, 99, 100], [100, 101, 95, 104]],
    [[100, 101, 99, 100], [100, 101, 99, 100], [100, 101, 99, 100], [100, 101, -5, 100]],
])
def test_invalid_ohlc_rejected(rows):
    with pytest.raises(ValueError):
        run_sweep(frame(rows))


def test_overlarge_stop_filtered_without_rewriting_price():
    x = frame(base() + [[100, 100.2, 80.0, 99.4]])
    assert run_sweep(x) == []
