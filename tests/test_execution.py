import pandas as pd
import pytest

from norisk_quant.execution import run
from norisk_quant.model import Settings, Signal
from norisk_quant.report import report


def candles(items):
    times = pd.to_datetime([x[0] for x in items], utc=True)
    return pd.DataFrame(
        [{"o": x[1], "h": x[2], "l": x[3], "c": x[4]} for x in items],
        index=times,
    )


def signal(at="2020-01-01T00:01:00Z", side=1):
    return Signal(pd.Timestamp(at), side, 1.0, 2.0, "test")


def test_flat_trade_pays_only_40_cents_per_ounce():
    bars = candles([
        ("2020-01-01T00:00:00Z", 100, 100, 100, 100),
        ("2020-01-01T00:01:00Z", 100, 100, 100, 100),
        ("2020-01-01T00:02:00Z", 100, 100, 100, 100),
    ])
    result = run(bars, [signal()], Settings(ounces=2))
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["cost"] == pytest.approx(0.8)
    assert trade["net_pnl"] == pytest.approx(-0.8)
    assert trade["exit_reason"] == "end_of_data"


def test_same_minute_ambiguous_tp_sl_is_stopped_first():
    bars = candles([
        ("2020-01-01T00:00:00Z", 100, 100, 100, 100),
        ("2020-01-01T00:01:00Z", 100, 103, 98, 100),
    ])
    result = run(bars, [signal()], Settings())
    trade = result.trades.iloc[0]
    assert trade["exit_reason"] == "ambiguous_stop_first"
    assert trade["exit_price"] == 99
    assert trade["net_pnl"] == pytest.approx(-1.4)


def test_gap_through_stop_gets_worse_first_available_open():
    bars = candles([
        ("2020-01-01T00:00:00Z", 100, 100, 100, 100),
        ("2020-01-01T00:01:00Z", 100, 100, 100, 100),
        ("2020-01-01T00:10:00Z", 96, 97, 95, 96),
    ])
    result = run(bars, [signal()], Settings())
    trade = result.trades.iloc[0]
    assert trade["exit_price"] == 96
    assert trade["net_pnl"] == pytest.approx(-4.4)
    assert trade["exit_reason"] == "gap_stop"
    assert trade["gap_minutes"] == 8


def test_short_trade_target_and_fixed_fee():
    bars = candles([
        ("2020-01-01T00:00:00Z", 100, 100, 100, 100),
        ("2020-01-01T00:01:00Z", 100, 100, 97, 98),
    ])
    result = run(bars, [signal(side=-1)], Settings())
    trade = result.trades.iloc[0]
    assert trade["exit_price"] == 98
    assert trade["net_pnl"] == pytest.approx(1.6)


def test_stale_signal_is_not_entered_after_market_closure():
    bars = candles([
        ("2020-01-01T00:00:00Z", 100, 100, 100, 100),
        ("2020-01-01T00:10:00Z", 100, 100, 100, 100),
    ])
    result = run(bars, [signal()], Settings(max_entry_delay_minutes=1))
    assert result.trades.empty


def test_signal_from_future_is_never_traded():
    bars = candles([
        ("2020-01-01T00:00:00Z", 100, 100, 100, 100),
        ("2020-01-01T00:01:00Z", 100, 100, 100, 100),
    ])
    result = run(bars, [signal("2020-01-01T00:02:00Z")], Settings())
    assert result.trades.empty


def test_week_month_report_has_realized_and_equity(tmp_path):
    bars = candles([
        ("2020-01-01T00:00:00Z", 100, 100, 100, 100),
        ("2020-01-01T00:01:00Z", 100, 103, 100, 102),
    ])
    settings = Settings()
    result = run(bars, [signal()], settings)
    summary = report(result, settings, tmp_path)
    assert summary["net_pnl"] == pytest.approx(1.6)
    assert summary["positive_months"] == 1
    assert (tmp_path / "weekly.csv").is_file()
    assert (tmp_path / "monthly.csv").is_file()
    assert (tmp_path / "equity_m1.csv").is_file()
    monthly = pd.read_csv(tmp_path / "monthly.csv")
    assert monthly.iloc[0]["net_pnl"] == pytest.approx(1.6)


def test_invalid_settings_and_signal_are_rejected():
    with pytest.raises(ValueError):
        Settings(roundtrip_cost_per_ounce=-1)
    with pytest.raises(ValueError):
        Signal(pd.Timestamp("2020-01-01", tz="UTC"), 1, -1, 2)
