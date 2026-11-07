from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from norisk_quant.accounting import validate_execution
from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings, Signal
from norisk_quant.quote_stress import quote_stress_features, quote_stress_signals, qs01_settings


def quotes(count=300):
    index = pd.date_range("2012-01-02", periods=count, freq="min", tz="UTC")
    return pd.DataFrame({"o": 100., "h": 100.1, "l": 99.9, "c": 100., "ac": 100.2}, index=index)


def shock(frame, row=250, side=1):
    frame = frame.copy()
    frame.iloc[row, frame.columns.get_loc("c")] = 100 + side * 0.6
    frame.iloc[row, frame.columns.get_loc("h")] = max(100.1, 100 + side * 0.6)
    frame.iloc[row, frame.columns.get_loc("l")] = min(99.9, 100 + side * 0.6)
    frame.iloc[row, frame.columns.get_loc("ac")] = 100 + side * 0.6 + 0.7
    return frame


def test_frozen_signal_is_close_confirmed_reversal_and_prior_atr():
    frame = shock(quotes())
    signals = quote_stress_signals(frame)
    assert len(signals) == 1
    signal = signals[0]
    assert signal.confirmed_at == frame.index[250] + pd.Timedelta(minutes=1)
    assert signal.side == -1
    assert signal.stop_distance == pytest.approx(0.3)
    assert signal.target_distance == signal.stop_distance
    expanded = frame.copy()
    expanded.iloc[250, expanded.columns.get_loc("h")] = 120
    assert quote_stress_signals(expanded)[0] == signal  # shock's own range excluded


def test_features_and_signals_are_prefix_invariant():
    frame = shock(quotes())
    pd.testing.assert_frame_equal(quote_stress_features(frame).iloc[:251], quote_stress_features(frame.iloc[:251]))
    assert quote_stress_signals(frame.iloc[:251]) == quote_stress_signals(frame)
    future = frame.copy()
    future.iloc[251:, :] *= 5
    assert quote_stress_signals(future)[:1] == quote_stress_signals(frame)[:1]


def test_wilder_sma_seed_and_previous_close_true_range():
    frame = quotes()
    frame.iloc[20, frame.columns.get_loc("h")] = 101
    features = quote_stress_features(frame)
    # First 19 TRs .2, twentieth 1.1; prior ATR on row21 excludes row21.
    expected = (19 * .2 + 1.1) / 20
    assert features["prior_wilder_atr20"].iloc[21] == pytest.approx(expected)
    assert features["prior_wilder_atr20"].iloc[22] == pytest.approx((19 * expected + .2) / 20)


def test_contiguous_241_history_and_gap_reset():
    frame = shock(quotes(), row=239)
    assert not quote_stress_signals(frame)
    frame = shock(quotes(600), row=490)
    frame = frame.drop(frame.index[249])
    assert len(quote_stress_signals(frame)) == 1  # exactly 241 since first post-gap quote
    frame = shock(quotes(600), row=489).drop(quotes(600).index[249])
    assert not quote_stress_signals(frame)  # only 240 quotes since gap


@pytest.mark.parametrize("spread", [-.1, 0., .49, 3.01, np.nan, np.inf])
def test_spread_guards(spread):
    frame = shock(quotes())
    frame.iloc[250, frame.columns.get_loc("ac")] = frame["c"].iloc[250] + spread
    assert not quote_stress_signals(frame)


@pytest.mark.parametrize("field", ["max_holding_minutes"])
@pytest.mark.parametrize("value", [0, -1, 1.5, True, float("inf")])
def test_invalid_holding_cap(field, value):
    with pytest.raises(ValueError):
        Settings(**{field: value})


def execution_case(frame, signals, settings):
    reference, fast = run(frame, signals, settings), run_fast(frame, signals, settings)
    pd.testing.assert_frame_equal(reference.trades, fast.trades, check_dtype=False)
    pd.testing.assert_frame_equal(reference.equity, fast.equity, check_dtype=False)
    assert reference.pending_at_end == fast.pending_at_end
    assert reference.expired_signals == fast.expired_signals
    validate_execution(reference, settings)
    validate_execution(fast, settings)
    return reference


def test_time_exit_precedes_current_range_and_disallows_same_m1_reentry():
    frame = quotes(40)
    frame.loc[frame.index[30], ["h", "l"]] = [130, 70]
    signals = [Signal(frame.index[0], 1, 10, 10), Signal(frame.index[30], -1, 10, 10)]
    result = execution_case(frame, signals, qs01_settings())
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["exit_reason"] == "time_exit"
    assert result.trades.iloc[0]["closed_at"] == frame.index[30]
    assert result.trades.iloc[0]["cost"] == .4
    assert result.trades.iloc[0]["net_pnl"] == -.4


def test_time_exit_waits_for_first_observed_open_and_carries_gap_exposure():
    frame = quotes(50).drop(quotes(50).index[25:40])
    result = execution_case(frame, [Signal(frame.index[0], 1, 10, 10)], qs01_settings())
    trade = result.trades.iloc[0]
    assert trade["closed_at"] == pd.Timestamp("2012-01-02 00:40Z")
    assert trade["exit_reason"] == "time_exit"
    assert trade["gap_minutes"] == 15


def test_adverse_gap_stop_precedes_due_time_exit():
    frame = quotes(50).drop(quotes(50).index[25:40])
    frame.loc[frame.index[25], ["o", "h", "l", "c"]] = [85, 86, 84, 85]
    result = execution_case(frame, [Signal(frame.index[0], 1, 10, 10)], qs01_settings())
    assert result.trades.iloc[0]["exit_reason"] == "gap_stop"
    assert result.trades.iloc[0]["exit_price"] == 85
    assert result.trades.iloc[0]["net_pnl"] == -15.4


def test_next_open_gap_cannot_fill_and_stop_first_fee_once():
    frame = quotes(5).drop(quotes(5).index[1])
    settings = qs01_settings()
    result = execution_case(frame, [Signal(pd.Timestamp("2012-01-02 00:01Z"), 1, .1, .1)], settings)
    assert result.trades.empty
    assert result.expired_signals == 1
    frame = quotes(5)
    frame.loc[frame.index[1], ["h", "l"]] = [101, 99]
    result = execution_case(frame, [Signal(frame.index[1], 1, .5, .5)], settings)
    assert result.trades.iloc[0]["exit_reason"] == "ambiguous_stop_first"
    assert result.trades.iloc[0]["net_pnl"] == pytest.approx(-.9)


def test_fractional_quantity_time_exit_fee_once():
    settings = replace(qs01_settings(), ounces=.25)
    frame = quotes(40)
    result = execution_case(frame, [Signal(frame.index[0], 1, 10, 10)], settings)
    assert result.trades.iloc[0]["cost"] == .1
    assert result.equity.iloc[1]["floating_pnl"] == -.1
    assert result.equity.iloc[-1]["equity"] == -.1


def test_quote_spread_predictor_is_not_an_added_execution_charge():
    frame = shock(quotes(310))
    signals = quote_stress_signals(frame)
    result = execution_case(frame, signals, qs01_settings())
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "time_exit"
    assert trade["entry_price"] == 100
    assert trade["cost"] == .4
    assert trade["net_pnl"] == -.4


def test_signal_does_not_peek_at_next_gap_and_execution_expires_it():
    full = shock(quotes(310))
    missing_next = full.drop(full.index[251])
    signals = quote_stress_signals(missing_next)
    assert signals == quote_stress_signals(full)
    result = execution_case(missing_next, signals, qs01_settings())
    assert result.trades.empty
    assert result.expired_signals == 1
