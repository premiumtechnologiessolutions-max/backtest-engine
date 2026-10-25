import math

import pandas as pd
import pytest

from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings, Signal


def flat_bars():
    times = pd.date_range("2024-01-02T00:00:00Z", periods=4, freq="min")
    return pd.DataFrame({
        "o": [100.] * 4, "h": [100.] * 4,
        "l": [100.] * 4, "c": [100.] * 4,
    }, index=times)


def test_fractional_second_signal_can_only_enter_after_confirmation():
    # Regression: int(epoch_seconds) silently truncated .500 seconds and
    # previously let the fast engine enter 0.5s BEFORE the signal existed.
    market = flat_bars()
    signal = Signal(
        pd.Timestamp("2024-01-02T00:01:00.500Z"), 1, 1, 2, "timing"
    )
    first = run(market, [signal], Settings())
    optimized = run_fast(market, [signal], Settings())
    expected_entry = pd.Timestamp("2024-01-02T00:02:00Z")
    assert first.trades.iloc[0]["entry_at"] == expected_entry
    assert optimized.trades.iloc[0]["entry_at"] == expected_entry
    assert first.trades.iloc[0]["signal_at"] == signal.confirmed_at
    assert optimized.trades.iloc[0]["signal_at"] == signal.confirmed_at
    pd.testing.assert_frame_equal(first.trades, optimized.trades, check_dtype=False)
    pd.testing.assert_frame_equal(first.equity, optimized.equity, check_dtype=False)


def test_both_engines_expire_subsecond_signal_if_quote_resumes_too_late():
    market = flat_bars().iloc[[0, 3]]
    signal = Signal(pd.Timestamp("2024-01-02T00:01:00.500Z"), 1, 1, 2)
    expected = run(market, [signal], Settings(max_entry_delay_minutes=1))
    fast = run_fast(market, [signal], Settings(max_entry_delay_minutes=1))
    assert expected.trades.empty
    assert fast.trades.empty
    assert expected.expired_signals == fast.expired_signals == 1


def test_both_engines_fail_on_not_exact_m1_timestamps():
    market = flat_bars()
    market.index = market.index + pd.Timedelta(milliseconds=500)
    with pytest.raises(ValueError, match="minute boundaries"):
        run(market, [], Settings())
    with pytest.raises(ValueError, match="minute boundaries"):
        run_fast(market, [], Settings())


def test_nonfinite_prices_are_rejected_in_reference_and_fast():
    market = flat_bars()
    market.loc[market.index[1], "h"] = float("nan")
    with pytest.raises(ValueError, match="Bad OHLC"):
        run(market, [], Settings())
    with pytest.raises(ValueError, match="Invalid M1 OHLC"):
        run_fast(market, [], Settings())


@pytest.mark.parametrize("kwargs", [
    {"ounces": float("nan")}, {"ounces": float("inf")},
    {"roundtrip_cost_per_ounce": float("nan")},
    {"roundtrip_cost_per_ounce": float("inf")},
])
def test_risk_settings_reject_nonfinite_numbers(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


@pytest.mark.parametrize("stop,target", [
    (float("nan"), 2), (float("inf"), 2), (1, float("nan")), (1, float("inf")),
])
def test_signal_risk_distances_must_be_finite(stop, target):
    with pytest.raises(ValueError):
        Signal(pd.Timestamp("2024-01-02", tz="UTC"), 1, stop, target)
