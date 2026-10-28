"""Synthetic-only year-coverage gates for the independent 13-field replay.

One M1 candle per month proves only calendar-month presence, never broker
session completeness, tick fidelity, or fresh out-of-sample validity.
"""
from pathlib import Path

import pandas as pd
import pytest

import scripts.verify_bos_h1_parity as replay


def _year_sample(year=2012):
    return pd.DataFrame(
        {"o": [2000.0] * 12},
        index=pd.date_range(f"{year}-01-01T00:00:00Z", periods=12, freq="MS"),
    )


def test_replay_market_year_accepts_twelve_observed_months():
    replay.validate_replay_market_year(_year_sample(), 2012)


@pytest.mark.parametrize("month", [1, 6, 12])
def test_replay_market_year_rejects_missing_month(month):
    m1 = _year_sample()
    m1 = m1.loc[m1.index.month != month]
    with pytest.raises(ValueError, match="omits calendar months"):
        replay.validate_replay_market_year(m1, 2012)


def test_replay_market_year_rejects_wrong_year():
    with pytest.raises(ValueError, match="outside 2013"):
        replay.validate_replay_market_year(_year_sample(), 2013)


def test_replay_market_year_rejects_empty_input():
    with pytest.raises(ValueError, match="nonempty sorted unique UTC"):
        replay.validate_replay_market_year(_year_sample().iloc[:0], 2012)


def test_replay_market_year_rejects_timezone_naive_index():
    m1 = _year_sample()
    m1.index = m1.index.tz_localize(None)
    with pytest.raises(ValueError, match="nonempty sorted unique UTC"):
        replay.validate_replay_market_year(m1, 2012)


def test_replay_market_year_rejects_duplicate_timestamps():
    m1 = pd.concat([_year_sample(), _year_sample().iloc[:1]])
    with pytest.raises(ValueError, match="nonempty sorted unique UTC"):
        replay.validate_replay_market_year(m1, 2012)


def test_replay_market_year_rejects_unsorted_timestamps():
    m1 = _year_sample().iloc[::-1]
    with pytest.raises(ValueError, match="nonempty sorted unique UTC"):
        replay.validate_replay_market_year(m1, 2012)


def test_replay_market_year_rejects_non_datetime_index():
    m1 = _year_sample()
    m1.index = range(len(m1))
    with pytest.raises(ValueError, match="nonempty sorted unique UTC"):
        replay.validate_replay_market_year(m1, 2012)


def test_verify_rejects_missing_month_before_strategy_execution(monkeypatch):
    # Source-hash precondition is mocked ONLY for synthetic gate testing.
    # This is not a replay of the private original Gold data.zip.
    monkeypatch.setattr(replay, "file_sha256", lambda _: replay.EXPECTED_MARKET_SHA256)
    monkeypatch.setattr(replay, "read_reference_csv", lambda *a, **k: pd.DataFrame())
    incomplete = _year_sample().loc[lambda f: f.index.month != 6]
    monkeypatch.setattr(replay, "load_market", lambda *a, **k: incomplete)

    def strategy_must_not_run(*args, **kwargs):
        raise AssertionError("Strategy executed on incomplete annual M1")

    monkeypatch.setattr(replay, "bos_fib_limit_orders", strategy_must_not_run)
    with pytest.raises(ValueError, match="omits calendar months"):
        replay.verify(Path("synthetic-no-archive.zip"), Path("synthetic-ledger"), [2012])
