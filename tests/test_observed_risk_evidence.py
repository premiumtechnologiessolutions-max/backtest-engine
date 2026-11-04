"""Risk-control engineering tests using modeled synthetic equity marks only."""
import math

import pandas as pd
import pytest

from norisk_quant.observed_risk_evidence import (
    RiskLimits, observed_risk_evidence,
)


def equity(values, idx=None):
    if idx is None:
        idx = pd.date_range("2026-01-05T00:00:00Z",
                            periods=len(values), freq="min")
    return pd.DataFrame({"equity": values}, index=idx)


def test_peak_and_daily_risk_detect_drawdown_not_just_negative_total():
    rows = equity([0.0, 2.0, 1.0, -3.0, -2.0, 1.0])
    result = observed_risk_evidence(rows, RiskLimits(4.0, 4.0))
    assert result["max_observed_peak_drawdown_usd"] == 5.0
    assert result["max_observed_intraday_drawdown_usd"] == 5.0
    assert result["observed_limit_breached"] is True
    assert result["status"] == "OBSERVED_RISK_LIMIT_BREACH"
    assert result["independent_research_result_accepted"] is False


def test_gap_is_reported_as_unknown_not_silently_filled():
    idx = pd.to_datetime([
        "2026-01-05T00:00:00Z",
        "2026-01-05T00:01:00Z",
        "2026-01-05T00:08:00Z"])
    result = observed_risk_evidence(equity([0, 1, 1], idx))
    assert result["unobserved_minutes_between_marks"] == 6
    assert result["gaps_between_marks"] == 1
    assert result["status"] == "OBSERVED_ONLY_GAPPED_UNCERTIFIED"
    assert result["actual_intrabar_drawdown_unknown"] is True


def test_utc_midnight_without_gap_carries_observed_equity():
    idx = pd.to_datetime([
        "2026-01-05T23:59:00Z",
        "2026-01-06T00:00:00Z",
        "2026-01-06T00:01:00Z"])
    result = observed_risk_evidence(equity([3.0, 2.0, 0.0], idx))
    assert result["utc_days_observed"] == 2
    assert result["max_observed_intraday_drawdown_usd"] == 3.0
    assert result["gaps_between_marks"] == 0


def test_weekend_gap_does_not_infer_missing_intraday_equity():
    idx = pd.to_datetime([
        "2026-01-02T23:59:00Z",
        "2026-01-05T00:00:00Z"])
    result = observed_risk_evidence(equity([10.0, 9.0], idx))
    assert result["unobserved_minutes_between_marks"] > 100
    assert result["max_observed_intraday_drawdown_usd"] == 0.0
    assert result["max_observed_peak_drawdown_usd"] == 1.0
    assert result["status"] == "OBSERVED_ONLY_GAPPED_UNCERTIFIED"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_risk_marks_rejected(bad):
    with pytest.raises(ValueError, match="nonfinite"):
        observed_risk_evidence(equity([0.0, bad]))


def test_bools_strings_and_non_utc_or_duplicate_times_rejected():
    for frame in (
        equity([True, False]),
        equity(["0", "1"]),
        equity([0, 1], pd.date_range("2026-01-05", periods=2, freq="min")),
        equity([0, 1], pd.to_datetime(
            ["2026-01-05T00:00:00Z", "2026-01-05T00:00:00Z"])),
    ):
        with pytest.raises(ValueError):
            observed_risk_evidence(frame)


@pytest.mark.parametrize("value", [0, -1, float("nan"), True, float("inf")])
def test_risk_limits_are_strictly_positive_and_finite(value):
    with pytest.raises(ValueError):
        RiskLimits(value, 5.0)


def test_no_breach_is_not_broker_or_oos_certification():
    result = observed_risk_evidence(
        equity([0, 0.5, 0.1]), RiskLimits(10.0, 10.0))
    assert result["observed_limit_breached"] is False
    assert result["status"] == "OBSERVED_ONLY_NOT_BROKER_VALIDATED"
    assert result["broker_equity_reconciled"] is False
    assert result["live_trading_authorized"] is False
