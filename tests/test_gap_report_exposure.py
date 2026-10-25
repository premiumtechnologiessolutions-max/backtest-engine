import pandas as pd
import pytest

from norisk_quant.execution import run
from norisk_quant.model import Settings, Signal
from norisk_quant.report import report


def _bars(points):
    return pd.DataFrame(
        [{"o": o, "h": h, "l": l, "c": c} for _, o, h, l, c in points],
        index=pd.to_datetime([ts for ts, *_ in points], utc=True),
    )


def test_active_session_gap_trade_is_flagged_in_reports(tmp_path):
    frame = _bars(
        [
            ("2024-07-17T14:00:00Z", 100, 100, 100, 100),
            ("2024-07-17T14:01:00Z", 100, 100, 100, 100),
            ("2024-07-17T14:20:00Z", 98, 100, 97, 99),
        ]
    )
    trades = run(
        frame,
        [Signal(pd.Timestamp("2024-07-17T14:01:00Z"), 1, 1.0, 2.0, "test")],
        Settings(),
    )
    summary = report(trades, Settings(), tmp_path)
    assert summary["gaps_needing_manual_review"] == 1
    assert summary["trades_exposed_to_uncertain_gaps"] == 1
    row = pd.read_csv(tmp_path / "trades.csv").iloc[0]
    assert row["gap_execution_review_required"]
    assert row["uncertain_gap_intervals"] == 1
    assert row["exit_reason"] == "gap_stop"
    monthly = pd.read_csv(tmp_path / "monthly.csv")
    assert monthly.iloc[0]["uncertain_gap_trades"] == 1
    assert monthly.iloc[0]["uncertain_gap_trades_net_pnl"] == pytest.approx(-2.4)


def test_normal_daily_reopen_gap_is_not_called_unknown(tmp_path):
    frame = _bars(
        [
            ("2024-01-10T21:59:00Z", 100, 100, 100, 100),
            ("2024-01-10T22:00:00Z", 100, 100, 100, 100),
            ("2024-01-10T23:00:00Z", 98, 100, 97, 99),
        ]
    )
    trades = run(
        frame,
        [Signal(pd.Timestamp("2024-01-10T22:00:00Z"), 1, 1.0, 2.0, "test")],
        Settings(),
    )
    summary = report(trades, Settings(), tmp_path)
    assert summary["gaps_over10_missing_minutes"] == 1
    assert summary["gaps_needing_manual_review"] == 0
    row = pd.read_csv(tmp_path / "trades.csv").iloc[0]
    assert row["gap_intervals_over10m"] == 1
    assert row["uncertain_gap_intervals"] == 0
    assert row["gap_execution_review_required"] == False
