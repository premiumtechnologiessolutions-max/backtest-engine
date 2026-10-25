"""Sparse-calendar M1 accounting: never pretend a missing month was observed."""
import pandas as pd
import pytest

from norisk_quant.model import Signal, Settings
from norisk_quant.execution import run
from norisk_quant.report import report
from norisk_quant.portfolio import PortfolioSettings, run_portfolio, write_portfolio_report


def sparse():
    index = pd.to_datetime(["2024-01-31T23:59:00Z", "2024-03-01T00:00:00Z"])
    return pd.DataFrame(
        {"o": [100., 100.], "h": [100., 100.],
         "l": [100., 100.], "c": [100., 100.]},
        index=index,
    )


def assert_sparse_months(path, observation_column, mark_column, change_column):
    monthly = pd.read_csv(path / "monthly.csv")
    assert monthly["period"].tolist() == ["2024-01", "2024-02", "2024-03"]
    assert monthly[observation_column].tolist() == [True, False, True]
    assert monthly[mark_column].tolist() == pytest.approx([-.4, -.4, -.4])
    assert monthly[change_column].tolist() == pytest.approx([-.4, 0., 0.])
    assert monthly["net_pnl"].tolist() == pytest.approx([0., 0., -.4])


def test_reference_report_missing_month_is_not_observed(tmp_path):
    bars = sparse()
    settings = Settings()
    result = run(bars, [Signal(bars.index[0], 1, 5, 5, "a")], settings)
    report(result, settings, tmp_path)
    assert_sparse_months(
        tmp_path, "month_has_observed_m1", "month_end_equity", "month_equity_change"
    )


def test_shared_portfolio_report_missing_month_is_not_observed(tmp_path):
    bars = sparse()
    settings = PortfolioSettings({"a": 1}, max_open_positions=1, max_total_ounces=1)
    result = run_portfolio(bars, [Signal(bars.index[0], 1, 5, 5, "a")], settings)
    write_portfolio_report(result, settings, tmp_path)
    assert_sparse_months(
        tmp_path, "has_observed_m1", "period_end_equity", "equity_change"
    )
