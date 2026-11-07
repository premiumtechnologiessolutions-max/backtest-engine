import pandas as pd
import pytest

from norisk_quant.accounting import validate_execution
from norisk_quant.fvg import fvg_midpoint_limit_orders
from norisk_quant.limit_engine import run_limits
from norisk_quant.model import Settings
from norisk_quant.report import report


def constructed_fvg_m1():
    idx = pd.date_range("2024-01-02T00:00Z", periods=182, freq="min")
    prices = pd.DataFrame(index=idx)
    for k in ("o", "h", "l", "c"):
        prices[k] = 100.
    # First H1 candle, then displacement middle, then third low > first high.
    prices.loc[idx[0:60], ["o", "h", "l", "c"]] = [101, 102, 98, 101]
    prices.loc[idx[60:120], ["o", "h", "l", "c"]] = [104, 105, 101, 104]
    prices.loc[idx[120:180], ["o", "h", "l", "c"]] = [106, 108, 103, 106]
    # The gap's midpoint is (103 + 102) / 2 = 102.5;
    # first candle low is 98, stop=97.9, TP=111.7
    prices.loc[idx[180], ["o", "h", "l", "c"]] = [106, 108, 102.5, 106]
    prices.loc[idx[181], ["o", "h", "l", "c"]] = [109, 112, 108, 111]
    return prices


def test_fvg_three_full_bars_then_limit_retest_not_earlier(tmp_path):
    df = constructed_fvg_m1()
    orders = fvg_midpoint_limit_orders(
        df, timeframe="H1", min_gap_usd=0.5,
        stop_buffer_usd=0.1, reward_to_risk=2, expiry_hours=20
    )
    assert len(orders) == 1
    order = orders[0]
    assert order.placed_at == pd.Timestamp("2024-01-02T03:00:00Z")
    assert order.side == 1
    assert order.price == pytest.approx(102.5)
    assert order.stop == pytest.approx(97.9)
    assert order.target == pytest.approx(111.7)

    settings = Settings()
    result = run_limits(df, orders, settings)
    assert len(result.trades) == 1
    row = result.trades.iloc[0]
    assert row["entry_at"] >= order.placed_at
    assert row["entry_price"] == pytest.approx(102.5)
    assert row["exit_reason"] == "target"
    assert row["net_pnl"] == pytest.approx(8.8)
    assert validate_execution(result, settings)["accounting_checks"] == "PASSED"
    report(result, settings, tmp_path)
    monthly = pd.read_csv(tmp_path / "monthly.csv")
    assert monthly.iloc[0]["net_pnl"] == pytest.approx(8.8)


def test_missing_hour_between_first_and_third_cannot_create_fake_fvg():
    data = constructed_fvg_m1().iloc[:180]
    data = data.drop(data.index[60:120])
    orders = fvg_midpoint_limit_orders(data, timeframe="H1", min_gap_usd=0.5)
    assert orders == []


def test_raises_on_unsupported_or_invalid_params():
    with pytest.raises(ValueError):
        fvg_midpoint_limit_orders(constructed_fvg_m1(), min_gap_usd=-1)
