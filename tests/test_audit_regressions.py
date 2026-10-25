"""Independent failure cases found while auditing shared execution accounting."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from norisk_quant.execution import run
from norisk_quant.limit_engine import run_limits
from norisk_quant.model import Settings, Signal
from norisk_quant.portfolio import (
    PortfolioSettings, run_portfolio, validate_portfolio, write_portfolio_report,
)
from norisk_quant.portfolio_limits import run_limit_portfolio
from norisk_quant.report import report


def fixture():
    index = pd.date_range("2024-01-02T00:00Z", periods=3, freq="min")
    market = pd.DataFrame({"o": [100.] * 3, "h": [101.] * 3,
                           "l": [100.] * 3, "c": [101.] * 3}, index=index)
    settings = PortfolioSettings({"a": 1.})
    signal = Signal(index[0], 1, 10., 20., "a")
    return market, signal, settings, run_portfolio(market, [signal], settings)


def fractional_position_count(result):
    frame = result.equity
    frame["open_positions"] = .5


@pytest.mark.parametrize("portfolio", [False, True])
def test_unobserved_month_and_resumption_do_not_get_invented_equity_changes(tmp_path, portfolio):
    index = pd.to_datetime(["2024-01-31T23:59Z", "2024-03-01T00:00Z"])
    market = pd.DataFrame({"o": [100., 101.], "h": [101., 102.],
                           "l": [100., 101.], "c": [101., 102.]}, index=index)
    signal = Signal(index[0], 1, 10., 20., "a")
    if portfolio:
        settings = PortfolioSettings({"a": 1.})
        write_portfolio_report(run_portfolio(market, [signal], settings), settings, tmp_path)
        equity_column, change_column = "period_end_equity", "equity_change"
    else:
        settings = Settings()
        report(run(market, [signal], settings), settings, tmp_path)
        equity_column, change_column = "month_end_equity", "month_equity_change"
    monthly = pd.read_csv(tmp_path / "monthly.csv")
    assert monthly[equity_column].iloc[[0, 2]].tolist() == pytest.approx([.6, 1.6])
    assert pd.isna(monthly[equity_column].iloc[1])
    assert monthly[change_column].iloc[0] == pytest.approx(.6)
    assert monthly[change_column].iloc[1:].isna().all()
    assert monthly["has_observations"].tolist() == [True, False, True]
    assert monthly["change_spans_unobserved_period"].tolist() == [False, False, True]
    assert monthly["change_since_last_observed_period"].iloc[2] == pytest.approx(1.)
    weekly = pd.read_csv(tmp_path / "weekly.csv")
    weekly_change = "equity_change" if portfolio else "week_equity_change"
    assert weekly.loc[~weekly["has_observations"], weekly_change].isna().all()
    assert weekly.loc[weekly["change_spans_unobserved_period"], weekly_change].isna().all()


@pytest.mark.parametrize("mutate,match", [
    (lambda result: result.trades.__setitem__("side", 0), "side"),
    (lambda result: result.trades.__setitem__("entry_price", -100.), "prices"),
    (lambda result: result.trades.__setitem__("exit_price", np.inf), "prices"),
    (lambda result: result.trades.__setitem__("signal_at", pd.NaT), "causality"),
    (lambda result: result.trades.__setitem__("entry_at", pd.Timestamp("2023-01-01T00:00Z")), "causality"),
    (lambda result: result.trades.__setitem__("exit_reason", "invented"), "exit reason"),
    (lambda result: result.trades.__setitem__("exit_reason", "target"), "exit price"),
    (lambda result: result.trades.__setitem__("exit_reason", "gap_stop"), "beyond its stop"),
    (lambda result: result.trades.__setitem__("exit_reason", "time_exit"), "holding cap"),
    (lambda result: result.trades.__setitem__("gap_minutes", -1), "gap minutes"),
    (fractional_position_count, "integers"),
    (lambda result: result.equity.loc.__setitem__((result.equity.index[0], "gross_open_ounces"), .5), "exposure chronology"),
])
def test_portfolio_audit_fails_closed_on_corrupt_trade_and_exposure_fields(mutate, match):
    _, _, settings, result = fixture()
    mutate(result)
    with pytest.raises(ValueError, match=match):
        validate_portfolio(result, settings)


def test_portfolio_closed_at_end_cannot_keep_a_fabricated_open_book():
    _, _, settings, result = fixture()
    result.equity.iloc[-1, result.equity.columns.get_loc("open_positions")] = 1
    result.equity.iloc[-1, result.equity.columns.get_loc("gross_open_ounces")] = 1.
    result.equity.iloc[-1, result.equity.columns.get_loc("floating_pnl")] = 99.
    result.equity.iloc[-1, result.equity.columns.get_loc("equity")] += 99.
    with pytest.raises(ValueError, match="exposure chronology|finish flat"):
        validate_portfolio(result, settings)


def test_single_limit_engine_rejects_candles_between_minute_boundaries():
    market, _, _, _ = fixture()
    market.index += pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="minute boundaries"):
        run_limits(market, [], Settings())


@pytest.mark.parametrize("kwargs", [
    {"max_open_positions": 1.5}, {"max_open_positions": True},
    {"max_entry_delay_minutes": np.nan}, {"max_entry_delay_minutes": True},
    {"max_holding_minutes": 0}, {"max_holding_minutes": 1.5},
    {"max_holding_minutes": True}, {"max_holding_minutes": np.inf},
])
def test_portfolio_settings_reject_invalid_clock_and_capacity_counts(kwargs):
    with pytest.raises(ValueError):
        PortfolioSettings({"a": 1.}, **kwargs)


def test_legacy_engines_cannot_silently_ignore_unified_holding_cap():
    market, _, _, _ = fixture()
    settings = PortfolioSettings({"a": 1.}, max_holding_minutes=30)
    for engine in (run_portfolio, run_limit_portfolio):
        with pytest.raises(ValueError, match="requires run_unified_portfolio"):
            engine(market, [], settings)
    # Also fail clearly if a caller supplies a settings object with that field
    # to the single-position limit adapter.
    with pytest.raises(ValueError, match="requires run_unified_portfolio"):
        run_limits(market, [], SimpleNamespace(max_holding_minutes=30))
