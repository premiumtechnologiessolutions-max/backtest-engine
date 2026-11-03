"""Synthetic F-06 regression: flat marks cannot contain floating P/L.

These checks validate execution-accounting invariants, not broker fills.
"""
from __future__ import annotations

import pandas as pd
import pytest

from norisk_quant.accounting import validate_execution
from norisk_quant.execution import Result, run
from norisk_quant.model import Settings, Signal


def _minutes():
    index = pd.date_range("2024-01-02", periods=6, freq="min", tz="UTC")
    return pd.DataFrame({
        "o": [2000.0, 2000.1, 2000.2, 2000.3, 2000.4, 2000.5],
        "h": [2000.3, 2000.4, 2000.5, 2000.6, 2000.7, 2000.8],
        "l": [1999.9, 2000.0, 2000.1, 2000.2, 2000.3, 2000.4],
        "c": [2000.1, 2000.2, 2000.3, 2000.4, 2000.5, 2000.6],
    }, index=index)


def test_no_trades_cannot_claim_transient_million_dollar_floating_pl():
    index = _minutes().index
    floating = [0.0, 0.0, 1_000_000.0, 0.0, 0.0, 0.0]
    equity = pd.DataFrame({
        "realized_pnl": [0.0] * len(index),
        "floating_pnl": floating,
        "equity": floating,
    }, index=index)
    result = Result(trades=pd.DataFrame(), equity=equity, pending_at_end=0)
    with pytest.raises(ValueError, match="Floating P/L without an open position"):
        validate_execution(result, Settings())


def test_valid_flat_no_trade_reference_run_still_passes():
    result = run(_minutes(), [], Settings())
    assert validate_execution(result, Settings())["accounting_checks"] == "PASSED"


def test_legitimate_occupied_marks_and_forced_end_close_still_pass():
    bars = _minutes()
    signal = Signal(bars.index[0] + pd.Timedelta(minutes=1), 1, 0.7, 4.0, "synthetic")
    result = run(bars, [signal], Settings())
    assert len(result.trades) == 1
    assert result.trades.iloc[0]["exit_reason"] == "end_of_data"
    assert validate_execution(result, Settings())["accounting_checks"] == "PASSED"


def test_unliquidated_position_requires_different_occupancy_contract():
    bars = _minutes()
    settings = Settings(close_at_end=False)
    signal = Signal(bars.index[0] + pd.Timedelta(minutes=1), 1, 0.7, 4.0, "synthetic")
    result = run(bars, [signal], settings)
    assert result.trades.empty  # A live position is absent from the closed-trade ledger.
    assert result.equity["floating_pnl"].abs().sum() > 0
    assert validate_execution(result, settings)["accounting_checks"] == "PASSED"
