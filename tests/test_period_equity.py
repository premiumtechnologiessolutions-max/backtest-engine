import pandas as pd
import pytest

from norisk_quant.execution import run
from norisk_quant.model import Settings, Signal
from norisk_quant.report import report


def test_monthly_realized_and_floating_equity_are_separate(tmp_path):
    # Entry late January, then held over the month boundary; closed
    # in February only because this tiny fixture ends there.
    times = pd.to_datetime([
        "2024-01-31T23:58:00Z",
        "2024-01-31T23:59:00Z",
        "2024-02-01T00:00:00Z",
    ], utc=True)
    bars = pd.DataFrame(
        {"o": [100., 100., 100.], "h": [100., 100., 100.],
         "l": [100., 100., 100.], "c": [100., 100., 100.]},
        index=times,
    )
    settings = Settings()
    positions = run(
        bars,
        [Signal(pd.Timestamp("2024-01-31T23:59:00Z"), 1, 5., 10., "month")],
        settings
    )
    summary = report(positions, settings, tmp_path)
    by_month = pd.read_csv(tmp_path / "monthly.csv")
    jan, feb = by_month.iloc[0], by_month.iloc[1]
    assert jan["trades"] == 0
    assert jan["net_pnl"] == pytest.approx(0)
    assert jan["month_equity_change"] == pytest.approx(-0.4)
    assert feb["trades"] == 1
    assert feb["net_pnl"] == pytest.approx(-0.4)
    assert feb["month_equity_change"] == pytest.approx(0)
    assert feb["synthetic_end_of_data_trades"] == 1
    assert summary["last_observed_equity"] == pytest.approx(-0.4)
