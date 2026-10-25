import pandas as pd
import pytest

from norisk_quant.accounting import validate_execution
from norisk_quant.execution import run
from norisk_quant.model import Settings, Signal
from norisk_quant.report import report


def _fixture():
    bars = pd.DataFrame(
        [
            {"o": 100, "h": 100, "l": 100, "c": 100},
            {"o": 100, "h": 100, "l": 100, "c": 100},
            {"o": 100, "h": 100, "l": 100, "c": 100},
        ],
        index=pd.date_range("2024-03-01T00:00Z", periods=3, freq="min"),
    )
    return bars, Signal(bars.index[1], 1, 10, 20, "accounting_demo")


def test_end_of_data_is_not_mislabeled_as_realized_broker_exit(tmp_path):
    bars, sig = _fixture()
    settings = Settings(ounces=2, roundtrip_cost_per_ounce=0.4)
    result = run(bars, [sig], settings)
    audit = validate_execution(result, settings)
    assert audit["accounting_checks"] == "PASSED"
    assert audit["forced_end_of_data_closures"] == 1
    assert audit["forced_end_of_data_pnl"] == pytest.approx(-0.8)
    summary = report(result, settings, tmp_path)
    assert summary["forced_end_of_data_closures"] == 1
    row = pd.read_csv(tmp_path / "monthly.csv").iloc[0]
    assert row["synthetic_end_of_data_trades"] == 1
    assert row["synthetic_end_of_data_net_pnl"] == pytest.approx(-0.8)


def test_double_counted_cost_fails_audit():
    bars, sig = _fixture()
    settings = Settings()
    result = run(bars, [sig], settings)
    result.trades.loc[0, "cost"] = 0.8
    with pytest.raises(ValueError, match="Fee drift"):
        validate_execution(result, settings)


def test_fake_profitable_trade_fails_math_audit():
    bars, sig = _fixture()
    settings = Settings()
    result = run(bars, [sig], settings)
    result.trades.loc[0, "net_pnl"] += 100
    with pytest.raises(ValueError, match="Net P/L mismatch"):
        validate_execution(result, settings)


def test_broken_floating_equity_is_rejected():
    bars, sig = _fixture()
    settings = Settings()
    result = run(bars, [sig], settings)
    result.equity.loc[bars.index[1], "equity"] += 1
    with pytest.raises(ValueError, match="Equity ledger"):
        validate_execution(result, settings)
