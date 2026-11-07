"""Standalone Limit replay must share the UTC and directional contracts of Market replay."""
import numpy as np
import pandas as pd
import pytest

from norisk_quant.accounting import validate_execution
from norisk_quant.limit_engine import LimitOrder, run_limits
from norisk_quant.model import Settings


def _bars():
    index = pd.date_range("2024-01-02T00:00:00Z", periods=3, freq="min")
    return pd.DataFrame(
        {"o": [101., 100.5, 104.], "h": [101., 101., 104.],
         "l": [101., 99.9, 104.], "c": [101., 100.5, 104.]},
        index=index,
    )


def _order(*, side=1, placed="2024-01-02T00:01:00Z",
           expires="2024-01-02T00:03:00Z"):
    return LimitOrder(
        placed_at=pd.Timestamp(placed), expires_at=pd.Timestamp(expires),
        side=side, price=100., stop=98., target=104., strategy="limit_contract",
    )


@pytest.mark.parametrize("bad_side", [
    True, False, 1.0, -1.0, float("nan"), "1", None,
])
def test_limit_order_rejects_nonintegral_or_boolean_side(bad_side):
    with pytest.raises(ValueError, match="integer"):
        _order(side=bad_side)


@pytest.mark.parametrize("side", [1, np.int64(1)])
def test_limit_order_accepts_integral_buy_side(side):
    assert _order(side=side).side == 1


def test_offset_placement_is_normalized_to_utc_trade_ledger():
    market = _bars()
    order = _order(
        placed="2024-01-02T02:01:00+02:00",
        expires="2024-01-02T02:03:00+02:00",
    )
    result = run_limits(market, [order], Settings())
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["signal_at"] == pd.Timestamp("2024-01-02T00:01:00Z")
    assert str(result.trades["signal_at"].dtype) == "datetime64[ns, UTC]"
    assert validate_execution(result, Settings())["accounting_checks"] == "PASSED"


def test_standalone_limit_rejects_non_utc_market_index():
    market = _bars()
    market.index = market.index.tz_convert("Europe/Athens")
    with pytest.raises(ValueError, match="UTC"):
        run_limits(market, [_order()], Settings())


def test_standalone_limit_rejects_missing_market_timestamp():
    market = _bars()
    market.index = pd.DatetimeIndex([pd.NaT, *market.index[1:]])
    with pytest.raises(ValueError, match="UTC"):
        run_limits(market, [_order()], Settings())
