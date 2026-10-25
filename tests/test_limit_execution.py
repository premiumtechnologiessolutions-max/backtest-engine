import pandas as pd
import pytest

from norisk_quant.accounting import validate_execution
from norisk_quant.limit_engine import LimitOrder, run_limits
from norisk_quant.model import Settings
from norisk_quant.report import report


def candles(data):
    return pd.DataFrame(
        [{"o": o, "h": h, "l": l, "c": c} for _, o, h, l, c in data],
        index=pd.to_datetime([d for d, *_ in data], utc=True)
    )


def buy(placed="2024-01-02T00:01:00Z", expires="2024-01-02T00:10:00Z"):
    return LimitOrder(
        placed_at=pd.Timestamp(placed), expires_at=pd.Timestamp(expires),
        side=1, price=100, stop=98, target=104, strategy="fvg_h1_ce_demo",
    )


def test_buy_limit_not_filled_before_price_touched():
    market = candles([
        ("2024-01-02T00:00:00Z", 103, 103, 102, 102),
        ("2024-01-02T00:01:00Z", 102, 103, 101, 102),
        ("2024-01-02T00:02:00Z", 102, 103, 99.5, 102),
        ("2024-01-02T00:03:00Z", 104, 105, 103, 104),
    ])
    r = run_limits(market, [buy()], Settings())
    assert len(r.trades) == 1
    row = r.trades.iloc[0]
    assert row["entry_at"] == pd.Timestamp("2024-01-02T00:02:00Z")
    assert row["entry_price"] == pytest.approx(100)
    assert row["exit_reason"] == "open_target"
    assert row["net_pnl"] == pytest.approx(3.6)
    validate_execution(r, Settings())


def test_both_target_and_stop_in_entry_minute_assumes_stop_first():
    market = candles([
        ("2024-01-02T00:00:00Z", 102, 102, 102, 102),
        ("2024-01-02T00:01:00Z", 102, 105, 97, 100),
    ])
    r = run_limits(market, [buy()], Settings())
    assert r.trades.iloc[0]["exit_reason"] == "ambiguous_stop_first"
    assert r.trades.iloc[0]["net_pnl"] == pytest.approx(-2.4)


def test_adverse_gap_open_beyond_stop_never_assumes_stop_price():
    market = candles([
        ("2024-01-02T00:00:00Z", 102, 102, 102, 102),
        ("2024-01-02T00:05:00Z", 95, 100, 94, 98),
    ])
    r = run_limits(market, [buy()], Settings())
    assert r.trades.iloc[0]["exit_reason"] == "entry_open_beyond_stop"
    assert r.trades.iloc[0]["exit_price"] == pytest.approx(95)
    assert r.trades.iloc[0]["net_pnl"] == pytest.approx(-5.4)
    validate_execution(r, Settings())


def test_expired_order_never_enters_after_reopen():
    market = candles([
        ("2024-01-02T00:00:00Z", 102, 102, 102, 102),
        ("2024-01-02T01:00:00Z", 100, 101, 99, 100),
    ])
    r = run_limits(market, [buy()], Settings())
    assert r.trades.empty
    assert r.expired_signals == 1


def test_limit_validation_rejects_wrong_risk_order():
    with pytest.raises(ValueError):
        LimitOrder(
            pd.Timestamp("2024-01-01", tz="UTC"),
            pd.Timestamp("2024-01-02", tz="UTC"),
            side=1, price=100, stop=101, target=105
        )
