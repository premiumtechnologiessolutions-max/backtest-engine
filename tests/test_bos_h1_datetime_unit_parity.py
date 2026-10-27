"""M1 BOS and causal H1 must not depend on pandas datetime storage resolution.

All prices are artificial; no raw market data, profit, or OOS claim.
"""
import math

import numpy as np
import pandas as pd
import pytest

from norisk_quant.bos_fib import bos_fib_limit_orders
from norisk_quant.h1_regime import complete_h1_regimes, filter_orders_h1
from norisk_quant.limit_engine import LimitOrder


def _bos_m1():
    ix = pd.date_range("2024-03-10T05:00:00Z", periods=440, freq="min")
    prices = np.array([
        100 + .075 * i + 1.7 * math.sin(i * .26)
        for i in range(len(ix))
    ])
    return pd.DataFrame(
        {"o": prices, "h": prices + .14, "l": prices - .14, "c": prices},
        index=ix,
    )


def _h1_m1():
    # Deliberately spans the New York spring DST transition, but UTC is
    # the authoritative candle clock and H1 bins are aligned to UTC.
    ix = pd.date_range("2024-03-08T00:00:00Z", periods=5000, freq="min")
    n = np.arange(len(ix))
    prices = 2000 + n * .03 + .25 * np.sin(n / 15)
    return pd.DataFrame(
        {"o": prices, "h": prices + .3, "l": prices - .3, "c": prices},
        index=ix,
    )


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_bos_orders_identical_for_all_datetime_units(unit):
    base = _bos_m1()
    expected = bos_fib_limit_orders(base)
    assert expected, "Synthetic fixture must generate BOS orders"
    alternative = base.copy()
    alternative.index = alternative.index.as_unit(unit)
    assert bos_fib_limit_orders(alternative) == expected


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_bos_gap_behavior_identical_for_all_datetime_units(unit):
    base = _bos_m1()
    first = bos_fib_limit_orders(base)[0]
    # Remove a short observed interval just before the first signal.
    missing = (
        (base.index >= first.placed_at - pd.Timedelta(minutes=6))
        & (base.index < first.placed_at)
    )
    base = base.loc[~missing]
    expected = bos_fib_limit_orders(base)
    alternative = base.copy()
    alternative.index = alternative.index.as_unit(unit)
    assert bos_fib_limit_orders(alternative) == expected


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_h1_regimes_and_filter_identical_for_all_datetime_units(unit):
    base = _h1_m1()
    candidate_time = pd.Timestamp("2024-03-10T18:00:00Z")
    order = LimitOrder(
        placed_at=candidate_time,
        expires_at=candidate_time + pd.Timedelta(minutes=10),
        side=1, price=2000., stop=1995., target=2005.,
    )
    expected_bars = complete_h1_regimes(base)
    expected_selected = filter_orders_h1(base, [order])
    assert expected_selected == [order], "Synthetic H1 fixture must have bullish trend"
    alternative = base.copy()
    alternative.index = alternative.index.as_unit(unit)
    actual_bars = complete_h1_regimes(alternative)
    # Storage resolution can differ, but all observed UTC bar instants
    # and derived causal H1 values must be identical.
    actual_bars.index = actual_bars.index.as_unit("ns")
    expected_bars.index = expected_bars.index.as_unit("ns")
    pd.testing.assert_frame_equal(actual_bars, expected_bars)
    assert filter_orders_h1(alternative, [order]) == expected_selected


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_h1_non_utc_index_is_equivalent_across_dst(unit):
    base = _h1_m1()
    alternative = base.copy()
    alternative.index = alternative.index.tz_convert("America/New_York").as_unit(unit)
    actual = complete_h1_regimes(alternative)
    expected = complete_h1_regimes(base)
    actual.index = actual.index.tz_convert("UTC").as_unit("ns")
    expected.index = expected.index.as_unit("ns")
    pd.testing.assert_frame_equal(actual, expected)


def test_bos_rejects_seconds_off_exact_minute():
    data = _bos_m1()
    data.index = data.index.as_unit("s")
    modified = data.index.tolist()
    modified[10] = modified[10] + pd.Timedelta(seconds=1)
    data.index = pd.DatetimeIndex(modified).as_unit("s")
    with pytest.raises(ValueError, match="minute boundaries"):
        bos_fib_limit_orders(data)


def test_h1_rejects_seconds_off_exact_minute():
    data = _h1_m1()
    data.index = data.index.as_unit("s")
    modified = data.index.tolist()
    modified[10] = modified[10] + pd.Timedelta(seconds=1)
    data.index = pd.DatetimeIndex(modified).as_unit("s")
    with pytest.raises(ValueError, match="minute boundaries"):
        complete_h1_regimes(data)
