"""Synthetic-only deterministic 13-field original replay gate tests.

No Gold archive, historic ledger, or private quote row is committed.
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.verify_original_bos_ledger_parity import (
    FIELDS, TOLERANCE, compare_trade_fields, validate_years, verify,
)


def sample():
    saved = pd.DataFrame({
        "signal_time": [1325769360], "entry_time": [1325769360],
        "side": [1], "entry": [100.123456], "stop": [99.5],
        "target": [101.0], "gap_minutes": [0],
        "exit_time": [1325769420], "exit": [99.5],
        "exit_reason": ["stop"], "gross": [-0.623456],
        "fee": [.40], "net": [-1.023456],
    })
    actual = pd.DataFrame({
        "signal_at": pd.to_datetime(["2012-01-05T13:16:00Z"]),
        "entry_at": pd.to_datetime(["2012-01-05T13:16:00Z"]),
        "side": [1], "entry_price": [100.123456],
        "stop": [99.5], "target": [101.0], "gap_minutes": [0],
        "closed_at": pd.to_datetime(["2012-01-05T13:17:00Z"]),
        "exit_price": [99.5], "exit_reason": ["stop"],
        "gross_pnl": [-0.623456], "cost": [.40], "net_pnl": [-1.023456],
    })
    return actual, saved


def test_all_thirteen_fields_match_without_return_only_shortcut():
    actual, saved = sample()
    outcome = compare_trade_fields(actual, saved)
    assert len(FIELDS) == 13
    assert outcome["fields_per_trade"] == 13
    assert outcome["trades"] == 1
    assert outcome["mismatched_fields"] == 0
    assert outcome["max_abs_numeric_difference"] == pytest.approx(0)


@pytest.mark.parametrize(("field", "replacement"), [
    ("entry", 100.123456 + 1e-5), ("stop", 99.0),
    ("target", 100.0), ("exit", 99.0), ("gross", 0),
    ("fee", 0), ("net", 0), ("signal_time", 1325769420),
    ("entry_time", 1325769420), ("exit_time", 1325769360),
    ("side", -1), ("gap_minutes", 1), ("exit_reason", "target"),
])
def test_each_execution_field_cannot_drift_silently(field, replacement):
    actual, saved = sample()
    saved.loc[0, field] = replacement
    with pytest.raises(AssertionError):
        compare_trade_fields(actual, saved)


@pytest.mark.parametrize(("which", "field", "bad"), [
    ("actual", "side", 1.5),
    ("archived", "side", 1.5),
    ("actual", "side", True),
    ("archived", "side", True),
    ("actual", "side", 0),
    ("archived", "side", 2),
    ("actual", "gap_minutes", 0.9),
    ("archived", "gap_minutes", 0.9),
    ("actual", "gap_minutes", True),
    ("archived", "gap_minutes", -1),
    ("actual", "gap_minutes", float("nan")),
])
def test_discrete_execution_fields_must_not_be_truncated_or_coerced(
        which, field, bad):
    actual, saved = sample()
    target = actual if which == "actual" else saved
    column = field
    # Deliberately preserve malformed values instead of allowing pandas
    # to cast booleans into the existing int64 column.
    target[column] = target[column].astype(object)
    target.at[0, column] = bad
    with pytest.raises(ValueError, match="discrete execution value"):
        compare_trade_fields(actual, saved)


@pytest.mark.parametrize("field", ["signal_time", "entry_time", "exit_time"])
def test_archived_fractional_epoch_seconds_are_never_truncated(field):
    actual, saved = sample()
    saved[field] = saved[field].astype(float)
    saved.at[0, field] += 0.5
    with pytest.raises(ValueError, match="Noncanonical discrete execution"):
        compare_trade_fields(actual, saved)


@pytest.mark.parametrize("field", ["signal_at", "entry_at", "closed_at"])
def test_actual_subsecond_execution_times_cannot_match_integer_archive(field):
    actual, saved = sample()
    actual.at[0, field] += pd.Timedelta(milliseconds=500)
    with pytest.raises(AssertionError, match="Subsecond timestamp drift"):
        compare_trade_fields(actual, saved)


def test_small_floating_error_respects_fixed_numeric_tolerance():
    actual, saved = sample()
    saved.loc[0, "entry"] += TOLERANCE / 20
    assert compare_trade_fields(actual, saved)["trades"] == 1


def test_fail_closed_on_ledger_count_column_and_naive_time():
    actual, saved = sample()
    with pytest.raises(AssertionError, match="counts"):
        compare_trade_fields(actual, pd.concat([saved, saved], ignore_index=True))
    with pytest.raises(ValueError, match="ledger"):
        compare_trade_fields(actual.drop(columns=["net_pnl"]), saved)
    actual["signal_at"] = actual["signal_at"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="UTC"):
        compare_trade_fields(actual, saved)


@pytest.mark.parametrize("years", [
    [], [2012,2012], [2011], [2020], [2012.0], [True],
])
def test_unsupported_years_rejected_before_private_io(years):
    with pytest.raises(ValueError):
        validate_years(years)


def test_unavailable_private_archive_fails_before_engine(tmp_path):
    with pytest.raises(ValueError, match="original Gold source"):
        verify(tmp_path/"missing_gold.zip", tmp_path/"missing_reference.zip", [2012])
