"""Synthetic independent source-price check for archived 13-field BOS/H1 replay.

No original Gold ZIP, private trade ledger or broker ticks are used here.
"""
import pandas as pd
import pytest

from scripts.verify_bos_h1_parity import (
    exact_ledger_check, validate_end_of_data_source_close,
)


def _matching_ledgers(*, exit_price=101.0, closed_at="2024-01-02T00:02:00Z",
                      reason="end_of_data"):
    signal = pd.Timestamp("2024-01-02T00:00:00Z")
    entry_at = pd.Timestamp("2024-01-02T00:01:00Z")
    exit_at = pd.Timestamp(closed_at)
    gross = exit_price - 100.0
    actual = pd.DataFrame([{
        "signal_at": signal, "entry_at": entry_at, "closed_at": exit_at,
        "side": 1, "entry_price": 100.0, "exit_price": exit_price,
        "stop": 99.0, "target": 102.0, "gross_pnl": gross,
        "cost": 0.40, "net_pnl": gross - 0.40,
        "exit_reason": reason, "gap_minutes": 0,
    }])
    archive = pd.DataFrame([{
        "signal_time": int(signal.timestamp()),
        "entry_time": int(entry_at.timestamp()),
        "exit_time": int(exit_at.timestamp()),
        "side": 1, "entry": 100.0, "exit": exit_price,
        "stop": 99.0, "target": 102.0, "gross": gross,
        "fee": 0.40, "net": gross - 0.40,
        "exit_reason": reason, "gap_minutes": 0,
    }])
    return actual, archive


def _source(*, final_close=101.0):
    return pd.DataFrame(
        {"c": [100.0, 100.5, final_close]},
        index=pd.date_range("2024-01-02T00:00:00Z", periods=3, freq="min"),
    )


def test_matching_end_of_data_ledgers_reconcile_to_last_source_bid_close():
    actual, archive = _matching_ledgers()
    assert exact_ledger_check(actual, archive)["trades"] == 1
    assert validate_end_of_data_source_close(_source(), actual) == 1


@pytest.mark.parametrize("last_close", [100.5, 101.5])
def test_identically_forged_final_price_matches_13_fields_but_fails_source(last_close):
    actual, archive = _matching_ledgers()
    assert exact_ledger_check(actual, archive)["trades"] == 1
    with pytest.raises(AssertionError, match="exit price differs"):
        validate_end_of_data_source_close(_source(final_close=last_close), actual)


def test_identically_forged_final_time_matches_13_fields_but_fails_source():
    actual, archive = _matching_ledgers(closed_at="2024-01-02T00:01:00Z")
    assert exact_ledger_check(actual, archive)["trades"] == 1
    with pytest.raises(AssertionError, match="timestamp differs"):
        validate_end_of_data_source_close(_source(), actual)


def test_only_one_forced_end_exit_possible_in_one_position_engine():
    actual, archive = _matching_ledgers()
    assert exact_ledger_check(pd.concat([actual, actual], ignore_index=True),
                              pd.concat([archive, archive], ignore_index=True))["trades"] == 2
    with pytest.raises(AssertionError, match="multiple forced"):
        validate_end_of_data_source_close(_source(), pd.concat([actual, actual]))


def test_nonforced_exit_needs_no_final_source_close_check():
    actual, _ = _matching_ledgers(exit_price=102.0, reason="target")
    assert validate_end_of_data_source_close(_source(final_close=100.5), actual) == 0


def test_forced_exit_requires_observed_source_close():
    actual, _ = _matching_ledgers()
    with pytest.raises(AssertionError, match="requires final UTC M1"):
        validate_end_of_data_source_close(pd.DataFrame(), actual)


def test_forced_exit_rejects_nonfinite_final_market_close():
    actual, _ = _matching_ledgers()
    with pytest.raises(AssertionError, match="exit price differs"):
        validate_end_of_data_source_close(_source(final_close=float("nan")), actual)
