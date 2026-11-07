"""Synthetic fail-closed monthly exit-ledger arithmetic integrity tests.

No private XAUUSD quotes or claims of new backtests.
"""
import pytest

from scripts.research_candidate_screen import drawdown, metrics


def test_zero_trade_month_cannot_book_realized_profit_or_loss():
    months = ["2024-01", "2024-02", "2024-03"]
    for impossible in (0.01, -0.01):
        with pytest.raises(ValueError, match="zero-trade"):
            metrics(months, dict(zip(months, [1.0, impossible, -2.0])),
                    dict(zip(months, [1, 0, 1])))


def test_genuine_zero_trade_flat_month_remains_valid():
    months = ["2024-01", "2024-02", "2024-03"]
    result = metrics(months, dict(zip(months, [1.0, 0.0, -2.0])),
                     dict(zip(months, [1, 0, 1])))
    assert result["zero_trade_months"] == 1
    assert result["positive_months"] == 1
    assert result["net_pnl_usd_per_oz"] == -1.0


def test_finite_inputs_cannot_overflow_cumulative_equity():
    with pytest.raises(ValueError, match="overflow"):
        drawdown([1e308, 1e308])


def test_finite_inputs_cannot_overflow_monthly_net_or_rolling_window():
    months = ["2024-01", "2024-02", "2024-03"]
    with pytest.raises(ValueError, match="overflow"):
        metrics(months, dict(zip(months, [1e308, 1e308, -1e308])),
                dict.fromkeys(months, 1))


def test_finite_inputs_cannot_overflow_peak_to_trough_drawdown():
    with pytest.raises(ValueError, match="overflow"):
        drawdown([1e308, -1e308, -1e308])
