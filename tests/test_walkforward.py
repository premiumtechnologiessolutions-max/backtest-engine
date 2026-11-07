import pandas as pd
import pytest

from norisk_quant.walkforward import (
    WalkForwardFold, fold_manifest, purge_cross_boundary_trades,
    require_training_only, year_folds,
)


def test_yearly_folds_are_chronological_and_embargoed():
    folds = year_folds(
        start_year=2012,
        last_year=2024,
        minimum_train_years=5,
        embargo_days=14,
    )
    assert len(folds) == 8
    f = folds[0]
    assert f.train_start_utc.startswith("2012-01-01")
    assert f.train_end_exclusive_utc.startswith("2016-12-18")
    assert f.eval_start_utc.startswith("2017-01-01")
    assert f.eval_end_exclusive_utc.startswith("2018-01-01")
    assert not f.evaluation_is_independent  # Historical years are exposed.
    assert len(fold_manifest(folds)) == 8


def test_train_selector_fails_if_eval_or_embargo_records_are_included():
    fold = year_folds(
        start_year=2012, last_year=2017, minimum_train_years=5,
        embargo_days=7,
    )[0]
    safe = pd.DataFrame({"closed_at": ["2016-12-01T00:00:00Z"]})
    require_training_only(safe, fold)
    unsafe = pd.DataFrame({"closed_at": ["2016-12-30T00:00:00Z"]})
    with pytest.raises(ValueError, match="includes embargo"):
        require_training_only(unsafe, fold)


def test_open_cross_boundary_trade_is_purged():
    fold = year_folds(
        start_year=2012, last_year=2017, minimum_train_years=5,
        embargo_days=7,
    )[0]
    frame = pd.DataFrame(
        {
            "entry_at": ["2016-12-15T00:00:00Z", "2016-12-18T00:00:00Z"],
            "closed_at": ["2016-12-17T00:00:00Z", "2017-01-02T00:00:00Z"],
        }
    )
    purged = purge_cross_boundary_trades(frame, fold)
    assert len(purged) == 1


def test_invalid_non_utc_fold_or_years_fail():
    with pytest.raises(ValueError):
        WalkForwardFold(
            "2012-01-01", "2013-01-01", "2013-01-01", "2014-01-01", 0
        )
    with pytest.raises(ValueError):
        year_folds(start_year=2024, last_year=2024)


@pytest.mark.parametrize("embargo", [7, True, 1.5, -1])
def test_manual_fold_cannot_fake_declared_embargo(embargo):
    # Only one actual day separates training and evaluation. A seven-day
    # declared embargo must not be accepted as if it were applied.
    with pytest.raises(ValueError, match="embargo|Embargo"):
        WalkForwardFold(
            "2012-01-01T00:00:00Z", "2016-12-31T00:00:00Z",
            "2017-01-01T00:00:00Z", "2018-01-01T00:00:00Z",
            embargo,
        )


def test_manual_fold_rejects_non_utc_boundaries():
    with pytest.raises(ValueError, match="UTC"):
        WalkForwardFold(
            "2012-01-01T01:00:00+01:00", "2016-12-25T00:00:00Z",
            "2017-01-01T00:00:00Z", "2018-01-01T00:00:00Z", 7,
        )


@pytest.mark.parametrize("bad_date", [
    "2016-12-01T00:00:00",  # Naive timestamps must never be assumed UTC.
    "2016-12-01T01:00:00+01:00",  # Same instant, wrong declared timezone.
    pd.NaT,  # A missing timestamp cannot silently disappear from training.
])
def test_training_selector_rejects_non_utc_or_missing_dates(bad_date):
    fold = year_folds(start_year=2012, last_year=2017, embargo_days=7)[0]
    frame = pd.DataFrame({"closed_at": [bad_date]})
    with pytest.raises(ValueError, match="UTC|missing"):
        require_training_only(frame, fold)


@pytest.mark.parametrize("entry,close", [
    ("2016-12-15T00:00:00", "2016-12-17T00:00:00Z"),
    ("2016-12-15T00:00:00Z", "2016-12-17T01:00:00+01:00"),
    ("2016-12-15T00:00:00Z", pd.NaT),
])
def test_purge_rejects_non_utc_or_missing_trade_timestamps(entry, close):
    fold = year_folds(start_year=2012, last_year=2017, embargo_days=7)[0]
    frame = pd.DataFrame({"entry_at": [entry], "closed_at": [close]})
    with pytest.raises(ValueError, match="UTC|missing"):
        purge_cross_boundary_trades(frame, fold)


@pytest.mark.parametrize("field,value", [
    ("start_year", True),
    ("last_year", 2024.0),
    ("minimum_train_years", True),
    ("test_years", 1.5),
    ("embargo_days", False),
])
def test_year_folds_rejects_boolean_or_fractional_parameters(field, value):
    params = dict(start_year=2012, last_year=2024)
    params[field] = value
    with pytest.raises(ValueError, match="integers"):
        year_folds(**params)
