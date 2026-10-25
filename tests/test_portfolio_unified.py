"""Mixed execution contracts, independent of licensed data or old research."""
import numpy as np
import pandas as pd
import pytest

from norisk_quant.limit_engine import LimitOrder
from norisk_quant.model import Signal
from norisk_quant.portfolio import PortfolioSettings, run_portfolio, validate_portfolio
from norisk_quant.portfolio_limits import run_limit_portfolio
from norisk_quant.portfolio_unified import run_unified_portfolio, write_unified_portfolio_report


def bars(rows, times=None):
    if times is None:
        times = pd.date_range("2024-01-02T00:00:00Z", periods=len(rows), freq="min")
    return pd.DataFrame(rows, index=times, columns=["o", "h", "l", "c"])


def limit(at, name="l", side=1, price=100, stop=95, target=105, expiry=10):
    return LimitOrder(at, at + pd.Timedelta(minutes=expiry), side, price, stop, target, name)


def test_mixed_stop_first_fractional_ounces_charge_exactly_one_fee():
    market = bars([[100, 106, 94, 100], [100, 100, 100, 100]])
    settings = PortfolioSettings({"m": .25, "l": 1.5}, max_open_positions=2, max_total_ounces=1.75)
    result = run_unified_portfolio(market, [Signal(market.index[0], 1, 5, 5, "m")],
                                   [limit(market.index[0], side=-1, stop=105, target=95)], settings)
    assert set(result.trades["order_type"]) == {"market", "limit"}
    assert result.trades["exit_reason"].tolist() == ["ambiguous_stop_first"] * 2
    assert result.trades["cost"].sum() == pytest.approx(.7)
    assert result.trades["net_pnl"].sum() == pytest.approx(-9.45)
    assert validate_portfolio(result, settings)["status"] == "PASSED"


def test_later_intrabar_limit_touch_cannot_steal_open_market_capacity():
    market = bars([[100, 100, 100, 100], [100, 103, 98, 100]])
    settings = PortfolioSettings({"a_limit": 1, "z_market": 1}, max_open_positions=1, max_total_ounces=1)
    older_limit = limit(market.index[0] + pd.Timedelta(seconds=30), "a_limit", price=99, stop=95)
    result = run_unified_portfolio(market, [Signal(market.index[1], 1, 5, 5, "z_market")],
                                   [older_limit], settings)
    assert result.trades["strategy"].tolist() == ["z_market"]
    assert result.capacity_rejected == 1
    assert result.pending_at_end == 0


def test_older_marketable_limit_has_priority_at_common_open():
    market = bars([[100, 100, 100, 100], [100, 103, 98, 100]])
    settings = PortfolioSettings({"z_limit": 1, "a_market": 1}, max_open_positions=1, max_total_ounces=1)
    older_limit = limit(market.index[0] + pd.Timedelta(seconds=30), "z_limit")
    result = run_unified_portfolio(market, [Signal(market.index[1], 1, 5, 5, "a_market")],
                                   [older_limit], settings)
    assert result.trades["strategy"].tolist() == ["z_limit"]
    assert result.capacity_rejected == 1


def test_market_and_limit_both_consume_ounce_capacity_even_after_instant_exit():
    market = bars([[100, 100, 100, 100], [90, 91, 89, 90]])
    settings = PortfolioSettings({"a": 1, "b": 1}, max_open_positions=2, max_total_ounces=1)
    orders = [limit(market.index[1], "a", price=100, stop=95)]
    result = run_unified_portfolio(market, [Signal(market.index[1], 1, 5, 5, "b")], orders, settings)
    assert result.trades["strategy"].tolist() == ["a"]
    assert result.trades.iloc[0]["exit_reason"] == "entry_open_beyond_stop"
    assert result.trades.iloc[0]["exit_price"] == 90
    assert result.capacity_rejected == 1


def test_old_exit_does_not_release_slot_to_either_order_type_this_minute():
    market = bars([[100, 100, 100, 100], [98, 98, 98, 98], [98, 98, 98, 98]])
    settings = PortfolioSettings({"old": 1, "m": 1, "l": 1}, max_open_positions=1, max_total_ounces=1)
    signals = [Signal(market.index[0], 1, 1, 5, "old"), Signal(market.index[1], 1, 1, 5, "m")]
    result = run_unified_portfolio(market, signals, [limit(market.index[1], price=98, stop=95)], settings)
    assert result.trades["strategy"].tolist() == ["old"]
    assert result.capacity_rejected == 2
    assert result.pending_at_end == 0


def test_limit_entry_target_deferred_market_target_known_from_open():
    market = bars([[100, 103, 100, 102], [102, 102, 102, 102]])
    settings = PortfolioSettings({"m": 1, "l": 1}, max_open_positions=2, max_total_ounces=2)
    result = run_unified_portfolio(market, [Signal(market.index[0], 1, 5, 2, "m")],
                                   [limit(market.index[0], target=102)], settings)
    indexed = result.trades.set_index("strategy")
    assert indexed.loc["m", "closed_at"] == market.index[0]
    assert indexed.loc["m", "exit_reason"] == "target"
    assert indexed.loc["l", "closed_at"] == market.index[1]
    assert indexed.loc["l", "exit_reason"] == "open_target"
    assert result.uncertain_entry_tp_deferred == 1


def test_carry_and_gap_through_on_shared_clock():
    times = pd.to_datetime(["2024-01-02T00:00Z", "2024-01-02T00:20Z"])
    market = bars([[100, 100, 100, 100], [90, 92, 89, 91]], times)
    settings = PortfolioSettings({"m": .5, "l": 2}, max_open_positions=2, max_total_ounces=2.5)
    result = run_unified_portfolio(market, [Signal(times[0], 1, 5, 10, "m")],
                                   [limit(times[0], target=110)], settings)
    assert result.trades["exit_reason"].tolist() == ["gap_stop", "gap_stop"]
    assert result.trades["gap_minutes"].tolist() == [19, 19]
    assert result.trades["net_pnl"].sum() == pytest.approx(-26)


def test_subsecond_signal_limit_expiry_and_pending_are_causal():
    market = bars([[100, 100, 100, 100]] * 3)
    when = market.index[0] + pd.Timedelta(milliseconds=1)
    settings = PortfolioSettings({"m": 1, "l": 1, "future": 1}, max_open_positions=3)
    result = run_unified_portfolio(
        market, [Signal(when, 1, 5, 5, "m"), Signal(market.index[-1] + pd.Timedelta(milliseconds=1), 1, 5, 5, "future")],
        [limit(when, expiry=0)], settings,
    )
    assert result.trades["strategy"].tolist() == ["m"]
    assert result.trades.iloc[0]["entry_at"] == market.index[1]
    assert result.expired_signals == 1
    assert result.pending_at_end == 1


def test_same_strategy_pending_cancelled_after_market_fill_and_not_reactivated():
    market = bars([[100, 100, 100, 100], [100, 101, 98, 100], [100, 101, 90, 100]])
    settings = PortfolioSettings({"a": 1}, max_open_positions=1, max_total_ounces=1)
    result = run_unified_portfolio(market, [Signal(market.index[1], 1, 1, 5, "a")],
                                   [limit(market.index[0], "a", price=92, stop=90)], settings)
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["order_type"] == "market"
    assert result.duplicate_strategy_rejected == 1
    assert result.pending_at_end == 0


def test_marked_open_fee_and_month_week_reports_reconcile(tmp_path):
    times = pd.to_datetime(["2024-03-31T23:59Z", "2024-04-01T00:00Z", "2024-04-01T00:01Z"])
    market = bars([[100, 101, 100, 101], [101, 102, 101, 102], [102, 103, 102, 103]], times)
    settings = PortfolioSettings({"m": .25, "l": .5}, max_open_positions=2, max_total_ounces=.75)
    result = run_unified_portfolio(market, [Signal(times[0], 1, 5, 10, "m")],
                                   [limit(times[0], target=110)], settings)
    assert result.equity.iloc[0]["floating_pnl"] == pytest.approx(.45)
    summary = write_unified_portfolio_report(result, settings, tmp_path)
    assert summary["status"] == "PASSED"
    assert summary["trades"] == 2
    for period in ("monthly", "weekly"):
        report = pd.read_csv(tmp_path / f"{period}.csv")
        assert len(report) == 2
        assert report["net_pnl"].sum() == pytest.approx(1.95)
        assert report["equity_change"].sum() == pytest.approx(1.95)
    assert result.equity.iloc[-1]["floating_pnl"] == 0
    assert result.trades["cost"].sum() == pytest.approx(.3)


def test_optional_open_book_reserves_full_roundtrip_fee():
    market = bars([[100, 102, 100, 101]])
    settings = PortfolioSettings({"m": .25, "l": .5}, max_open_positions=2,
                                 max_total_ounces=.75, close_at_end=False)
    result = run_unified_portfolio(market, [Signal(market.index[0], 1, 5, 10, "m")],
                                   [limit(market.index[0], target=110)], settings)
    assert result.trades.empty
    assert result.open_positions_at_end == 2
    assert result.equity.iloc[-1]["floating_pnl"] == pytest.approx(.45)


def test_pure_order_type_compatibility_and_seeded_mixed_shared_ledgers():
    for seed in range(5):
        rng = np.random.default_rng(seed)
        mid = 100 + np.cumsum(rng.normal(0, .1, 100))
        market = bars(np.column_stack([mid, mid + .2, mid - .2, mid]))
        signals = [Signal(market.index[n], 1 if n % 2 else -1, .25, .3, "m") for n in range(1, 95, 7)]
        orders = [limit(market.index[n], "l", price=mid[n], stop=mid[n] - .25,
                        target=mid[n] + .3, expiry=3) for n in range(1, 95, 7)]
        settings = PortfolioSettings({"m": .5, "l": 1}, max_open_positions=2, max_total_ounces=1.5)
        for old, new in (
            (run_portfolio(market, signals, settings), run_unified_portfolio(market, signals, [], settings)),
            (run_limit_portfolio(market, orders, settings), run_unified_portfolio(market, [], orders, settings)),
        ):
            pd.testing.assert_frame_equal(old.trades, new.trades.drop(columns="order_type"), check_dtype=False)
            pd.testing.assert_frame_equal(old.equity, new.equity, check_dtype=False)
        mixed = run_unified_portfolio(market, signals, orders, settings)
        assert validate_portfolio(mixed, settings)["status"] == "PASSED"


def test_time_exit_uses_open_before_later_intrabar_range():
    market = bars([[100, 100, 100, 100], [101, 110, 90, 100]])
    settings = PortfolioSettings({"m": 1, "l": 1}, max_open_positions=2,
                                 max_total_ounces=2, max_holding_minutes=1)
    result = run_unified_portfolio(market, [Signal(market.index[0], 1, 5, 5, "m")],
                                   [limit(market.index[0])], settings)
    assert result.trades["exit_reason"].tolist() == ["time_exit", "time_exit"]
    assert result.trades["exit_price"].tolist() == [101, 101]
    assert result.trades["net_pnl"].sum() == pytest.approx(1.2)


@pytest.mark.parametrize("opening,reason,price", [(90, "gap_stop", 90), (110, "open_target", 105),
                                                  (101, "time_exit", 101)])
def test_scheduled_exit_after_gap_respects_first_observed_price(opening, reason, price):
    times = pd.to_datetime(["2024-01-02T00:00Z", "2024-01-02T00:20Z"])
    market = bars([[100, 100, 100, 100], [opening, opening, opening, opening]], times)
    settings = PortfolioSettings({"m": 1}, max_holding_minutes=1)
    result = run_unified_portfolio(market, [Signal(times[0], 1, 5, 5, "m")], [], settings)
    assert result.trades.iloc[0]["exit_reason"] == reason
    assert result.trades.iloc[0]["exit_price"] == price


@pytest.mark.parametrize("field,value", [("max_open_positions", 1.5), ("max_entry_delay_minutes", float("nan")),
                                         ("all_in_cost_per_ounce", 0)])
def test_reject_noncanonical_or_invalid_settings_even_if_bypassed(field, value):
    settings = PortfolioSettings({"a": 1})
    object.__setattr__(settings, field, value)
    with pytest.raises(ValueError):
        run_unified_portfolio(bars([[100, 100, 100, 100]]), [], [], settings)


@pytest.mark.parametrize("mutation", ["subminute", "duplicate", "nan", "range"])
def test_invalid_source_data_fail_closed(mutation):
    market = bars([[100, 100, 100, 100]] * 2)
    if mutation == "subminute":
        market.index += pd.Timedelta(seconds=1)
    elif mutation == "duplicate":
        market.index = pd.DatetimeIndex([market.index[0]] * 2)
    elif mutation == "nan":
        market.loc[market.index[0], "o"] = np.nan
    else:
        market.loc[market.index[0], "h"] = 99
    with pytest.raises(ValueError):
        run_unified_portfolio(market, [], [], PortfolioSettings({"a": 1}))


def test_valid_microsecond_storage_index_still_has_whole_minute_opens():
    market = bars([[100, 100, 100, 100]] * 2)
    market.index = market.index.as_unit("us")
    result = run_unified_portfolio(market, [Signal(market.index[0], 1, 5, 5, "a")],
                                   [], PortfolioSettings({"a": 1}))
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["cost"] == pytest.approx(.4)


def test_future_prices_and_unavailable_instructions_cannot_change_equity_prefix():
    market = bars([[100, 101, 99, 100], [100, 102, 99, 101], [101, 103, 100, 102],
                   [102, 103, 100, 102]])
    settings = PortfolioSettings({"m": 1, "l": 1, "future": 1},
                                 max_open_positions=2, max_total_ounces=2, close_at_end=False)
    signals = [Signal(market.index[0], 1, 5, 10, "m"),
               Signal(market.index[-1], -1, 1, 2, "future")]
    orders = [limit(market.index[0], price=100, stop=95, target=110)]
    baseline = run_unified_portfolio(market, signals, orders, settings)
    changed = market.copy()
    changed.iloc[-1] = [200, 210, 190, 200]
    stressed = run_unified_portfolio(changed, signals, orders, settings)
    prefix = run_unified_portfolio(market.iloc[:-1], signals, orders, settings)
    pd.testing.assert_frame_equal(baseline.equity.iloc[:-1], stressed.equity.iloc[:-1])
    pd.testing.assert_frame_equal(baseline.equity.iloc[:-1], prefix.equity)
