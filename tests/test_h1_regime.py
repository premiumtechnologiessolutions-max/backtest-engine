"""Causal H1 regime gate regression; synthetic observed M1 minute candles."""
import numpy as np
import pandas as pd
import pytest

from norisk_quant.h1_regime import (
    H1RegimeSettings, complete_h1_regimes, filter_orders_h1,
)
from norisk_quant.limit_engine import LimitOrder


def synthetic_m1(n=3900):
    index = pd.date_range("2024-01-02T00:00:00Z", periods=n, freq="min")
    px = 2000 + np.arange(n) * 0.03 + 0.25 * np.sin(np.arange(n) / 15)
    return pd.DataFrame({
        "o": px, "h": px + 0.3, "l": px - 0.3, "c": px,
    }, index=index)


def order(when, side=1):
    at = pd.Timestamp(when)
    return LimitOrder(
        placed_at=at, expires_at=at + pd.Timedelta(minutes=10),
        side=side, price=2000.0,
        stop=1995.0 if side == 1 else 2005.0,
        target=2005.0 if side == 1 else 1995.0,
    )


def test_future_data_cannot_change_h1_decision():
    data = synthetic_m1()
    candidate = order("2024-01-04T15:00:00Z")
    selected = filter_orders_h1(data, [candidate])
    assert selected == [candidate]
    altered = data.copy()
    altered.loc[altered.index >= candidate.placed_at, ["o", "h", "l", "c"]] = [
        1900, 1901, 1899, 1900,
    ]
    assert filter_orders_h1(altered, [candidate]) == selected


def test_incomplete_hour_is_never_promoted():
    data = synthetic_m1()
    full = complete_h1_regimes(data)
    data = data.drop(data.index[-35:])
    incomplete = complete_h1_regimes(data)
    assert len(incomplete) <= len(full)
    assert incomplete["confirmed_at"].max() <= data.index[-1] + pd.Timedelta(minutes=1)


def test_short_history_is_neutral_not_future_filled():
    data = synthetic_m1(240)
    assert filter_orders_h1(
        data, [order("2024-01-02T03:00:00Z")]
    ) == []
    with pytest.raises(ValueError):
        H1RegimeSettings(ema_span=1)


def test_synthetic_H1_gate_not_moving_order_placement():
    data = synthetic_m1()
    entries = [
        order("2024-01-04T15:00:00Z"),
        order("2024-01-04T15:01:00Z", side=-1),
    ]
    passed = filter_orders_h1(data, entries)
    assert passed == entries[:1]
    assert passed[0].placed_at == entries[0].placed_at
