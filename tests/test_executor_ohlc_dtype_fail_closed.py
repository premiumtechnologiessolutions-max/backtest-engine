"""Synthetic fail-closed OHLC dtype controls for all three M1 executors.

The source loader may normalize text while parsing an authorized raw feed;
the executor must never independently reinterpret a corrupted cached or
manually supplied M1 DataFrame. No private market data or OOS used here.
"""
from __future__ import annotations

import pandas as pd
import pytest

from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.limit_engine import run_limits
from norisk_quant.model import Settings, Signal


def _market():
    index = pd.date_range("2024-03-04T10:00:00Z", periods=3, freq="min")
    return pd.DataFrame(
        {"o": [100.0, 100.0, 100.0],
         "h": [100.0, 101.0, 100.0],
         "l": [100.0, 100.0, 100.0],
         "c": [100.0, 100.5, 100.0]},
        index=index,
    )


def _execute(kind, market):
    settings = Settings(ounces=1.0, roundtrip_cost_per_ounce=0.40)
    if kind == "reference":
        return run(market, [], settings)
    if kind == "fast":
        return run_fast(market, [], settings)
    if kind == "limit":
        return run_limits(market, [], settings)
    raise AssertionError("Unknown synthetic executor")


@pytest.mark.parametrize("kind", ["reference", "fast", "limit"])
@pytest.mark.parametrize("column", ["o", "h", "l", "c"])
@pytest.mark.parametrize("invalid", ["numeric_text", "boolean", "mixed_object"])
def test_executor_rejects_coercible_non_numeric_quotes(kind, column, invalid):
    market = _market()
    if invalid == "numeric_text":
        market[column] = ["100.0", "100.0", "100.0"]
    elif invalid == "boolean":
        market[column] = [True, True, True]
    else:
        market[column] = pd.Series(
            [100.0, "100.0", 100.0], index=market.index, dtype=object
        )
    with pytest.raises(ValueError, match="numeric non-boolean dtype"):
        _execute(kind, market)


@pytest.mark.parametrize("kind", ["reference", "fast", "limit"])
def test_executor_rejects_duplicate_quote_column_names(kind):
    market = _market()
    market.columns = ["o", "h", "l", "o"]
    with pytest.raises(ValueError, match="columns must be unique"):
        _execute(kind, market)


@pytest.mark.parametrize("kind", ["reference", "fast", "limit"])
def test_executor_accepts_native_numeric_ohlc_without_trades(kind):
    market = _market().astype("float64")
    result = _execute(kind, market)
    assert result.trades.empty
    assert len(result.equity) == len(market)


def test_reference_fast_valid_trade_parity_unchanged():
    market = _market()
    signal = Signal(pd.Timestamp("2024-03-04T10:01:00Z"), 1, 1.0, 2.0, "fixture")
    settings = Settings(ounces=1.0, roundtrip_cost_per_ounce=0.40)
    reference = run(market, [signal], settings)
    fast = run_fast(market, [signal], settings)
    pd.testing.assert_frame_equal(reference.trades, fast.trades, check_dtype=False)
    pd.testing.assert_frame_equal(reference.equity, fast.equity, check_dtype=False)
    assert reference.trades.iloc[0]["cost"] == pytest.approx(0.40)
