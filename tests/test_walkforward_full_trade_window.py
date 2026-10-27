"""Regression tests: exit-booked training cannot include pre-train exposures."""
import pandas as pd
import pytest

from norisk_quant.walkforward import require_training_only, year_folds


def _fold():
    return year_folds(
        start_year=2012, last_year=2017, minimum_train_years=5,
        embargo_days=7,
    )[0]


def test_training_rejects_pre_train_entry_even_if_exit_is_inside():
    trades = pd.DataFrame({
        "entry_at": ["2011-12-31T23:59:00Z"],
        "closed_at": ["2012-01-02T00:00:00Z"],
    })
    with pytest.raises(ValueError, match="entry_at outside training"):
        require_training_only(trades, _fold())


def test_training_rejects_pre_train_signal_even_if_entry_and_exit_inside():
    trades = pd.DataFrame({
        "signal_at": ["2011-12-31T23:59:00Z"],
        "entry_at": ["2012-01-02T00:00:00Z"],
        "closed_at": ["2012-01-02T00:01:00Z"],
    })
    with pytest.raises(ValueError, match="signal_at outside training"):
        require_training_only(trades, _fold())


@pytest.mark.parametrize("entry,signal", [
    ("2016-12-02T00:00:00Z", "2016-12-01T00:00:00Z"),
    ("2016-12-01T00:00:00Z", "2016-12-02T00:00:00Z"),
])
def test_training_rejects_noncausal_trade_timestamps(entry, signal):
    trades = pd.DataFrame({
        "signal_at": [signal], "entry_at": [entry],
        "closed_at": ["2016-12-01T12:00:00Z"],
    })
    with pytest.raises(ValueError, match="after the subsequent trade event"):
        require_training_only(trades, _fold())


@pytest.mark.parametrize("bad", [
    "2016-12-01T00:00:00", "2016-12-01T01:00:00+01:00", pd.NaT,
])
def test_training_rejects_invalid_optional_entry_timestamp(bad):
    trades = pd.DataFrame({
        "entry_at": [bad], "closed_at": ["2016-12-01T00:01:00Z"],
    })
    with pytest.raises(ValueError, match="UTC|missing"):
        require_training_only(trades, _fold())


def test_training_accepts_complete_causal_utc_trade():
    trades = pd.DataFrame({
        "signal_at": ["2016-12-01T00:00:00Z"],
        "entry_at": ["2016-12-01T00:01:00Z"],
        "closed_at": ["2016-12-01T00:05:00Z"],
    })
    require_training_only(trades, _fold())


def test_training_still_accepts_closed_at_only_aggregate():
    summary = pd.DataFrame({"closed_at": ["2016-12-01T00:05:00Z"]})
    require_training_only(summary, _fold())


def test_training_rejects_embargo_entry_even_if_close_inside_training():
    trades = pd.DataFrame({
        "entry_at": ["2016-12-30T00:00:00Z"],
        "closed_at": ["2016-12-01T00:00:00Z"],
    })
    with pytest.raises(ValueError, match="entry_at outside training"):
        require_training_only(trades, _fold())
