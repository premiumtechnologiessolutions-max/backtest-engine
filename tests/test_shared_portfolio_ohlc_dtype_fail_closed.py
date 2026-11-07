"""Synthetic quote-schema contract for all three shared-capacity M1 portfolios.

No private Gold data, broker tick data or strategy performance is used.
These engines must not silently coerce text/bool OHLC after ingestion.
"""
from __future__ import annotations

import pandas as pd
import pytest

from norisk_quant.portfolio import PortfolioSettings, run_portfolio
from norisk_quant.portfolio_limits import run_limit_portfolio
from norisk_quant.portfolio_unified import run_unified_portfolio


def _market() -> pd.DataFrame:
    return pd.DataFrame(
        {"o": [100.0, 100.0, 100.0],
         "h": [101.0, 101.0, 101.0],
         "l": [99.0, 99.0, 99.0],
         "c": [100.0, 100.0, 100.0]},
        index=pd.date_range("2024-03-04T10:00:00Z", periods=3, freq="min"),
    )


def _execute(kind: str, market: pd.DataFrame):
    settings = PortfolioSettings({"synthetic": 1.0})
    if kind == "market":
        return run_portfolio(market, [], settings)
    if kind == "limit":
        return run_limit_portfolio(market, [], settings)
    if kind == "unified":
        return run_unified_portfolio(market, [], [], settings)
    raise AssertionError("Unknown shared-capacity executor")


@pytest.mark.parametrize("kind", ["market", "limit", "unified"])
@pytest.mark.parametrize("column", ["o", "h", "l", "c"])
@pytest.mark.parametrize("invalid", ["numeric_text", "boolean", "mixed_object"])
def test_shared_portfolios_reject_coercible_m1_quotes(kind, column, invalid):
    market = _market()
    if invalid == "numeric_text":
        market[column] = ["100.0"] * len(market)
    elif invalid == "boolean":
        market[column] = [True] * len(market)
    else:
        market[column] = pd.Series(
            [100.0, "100.0", 100.0], index=market.index, dtype=object,
        )
    with pytest.raises(ValueError, match="numeric non-boolean dtype"):
        _execute(kind, market)


@pytest.mark.parametrize("kind", ["market", "limit", "unified"])
def test_shared_portfolios_reject_duplicate_ohlc_column_names(kind):
    market = _market()
    market["extra"] = market["o"]
    market.columns = ["o", "h", "l", "c", "o"]
    with pytest.raises(ValueError, match="columns must be unique"):
        _execute(kind, market)


@pytest.mark.parametrize("kind", ["market", "limit", "unified"])
def test_shared_portfolios_accept_native_numeric_ohlc(kind):
    result = _execute(kind, _market())
    assert result.trades.empty
    assert len(result.equity) == 3
