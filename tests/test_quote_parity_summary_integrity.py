"""Synthetic fail-closed tests for tick-to-M1 parity summary integrity."""
import pandas as pd
import pytest

from norisk_quant.quote_parity import (
    compare_bid_ask_ticks_to_m1, summarize_bid_ask_parity,
)


def _report(with_missing=False):
    tick_index = pd.to_datetime([
        "2024-01-02T00:00:00Z", "2024-01-02T00:00:30Z",
    ], utc=True)
    ticks = pd.DataFrame(
        {"bid": [100., 101.], "ask": [100.4, 101.4]},
        index=tick_index,
    )
    m1_index = pd.to_datetime(
        ["2024-01-02T00:00:00Z"] +
        (["2024-01-02T00:01:00Z"] if with_missing else []),
        utc=True,
    )
    rows = [{"o": 100., "h": 101., "l": 100., "c": 101.,
             "ao": 100.4, "ah": 101.4, "al": 100.4, "ac": 101.4}]
    if with_missing:
        rows.append(dict(rows[0]))
    return compare_bid_ask_ticks_to_m1(ticks, pd.DataFrame(rows, index=m1_index))


@pytest.mark.parametrize("mutation", [
    "false_pass", "contradictory_mismatch", "fake_status",
    "nonboolean_flag", "missing_status", "missing_diff",
    "negative_diff", "nan_present_diff",
])
def test_summary_rejects_corrupted_parity_report(mutation):
    report = _report()
    if mutation == "false_pass":
        report["tick_present"] = False
    elif mutation == "contradictory_mismatch":
        report["bid_mismatch"] = True
    elif mutation == "fake_status":
        report["status"] = "NO_TICKS"
    elif mutation == "nonboolean_flag":
        report["both_quotes_match"] = 1
    elif mutation == "missing_status":
        report = report.drop(columns=["status"])
    elif mutation == "missing_diff":
        report = report.drop(columns=["ask_max_abs_diff"])
    elif mutation == "negative_diff":
        report["bid_max_abs_diff"] = -0.1
    elif mutation == "nan_present_diff":
        report["bid_max_abs_diff"] = float("nan")
    with pytest.raises(ValueError):
        summarize_bid_ask_parity(report)


@pytest.mark.parametrize("mutation", ["fake_match", "fake_mismatch", "fake_diff"])
def test_summary_rejects_corrupted_missing_tick_row(mutation):
    report = _report(with_missing=True)
    if mutation == "fake_match":
        report.loc[report.index[-1], "both_quotes_match"] = True
    elif mutation == "fake_mismatch":
        report.loc[report.index[-1], "ask_mismatch"] = True
    elif mutation == "fake_diff":
        report.loc[report.index[-1], "ask_max_abs_diff"] = 0.
    with pytest.raises(ValueError):
        summarize_bid_ask_parity(report)


def test_summary_preserves_valid_matched_missing_and_mismatched_results():
    complete = _report()
    assert summarize_bid_ask_parity(complete)["status"] == "PASSED_OBSERVED_OHLC_ONLY"
    missing = _report(with_missing=True)
    summary = summarize_bid_ask_parity(missing)
    assert summary["status"] == "FAILED_OR_INCOMPLETE"
    assert summary["missing_tick_minutes"] == 1
    mismatch = _report()
    mismatch["ask_mismatch"] = True
    mismatch["both_quotes_match"] = False
    mismatch["status"] = "QUOTE_MISMATCH"
    assert summarize_bid_ask_parity(mismatch)["quote_mismatch_minutes"] == 1
