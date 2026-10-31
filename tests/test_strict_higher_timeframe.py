"""Regression for historical incomplete-candle weakness in legacy XAUUSD research.

Legacy source scripts accepted H4 170/240 or H1 45/60 observed
minutes, and this changed strategy decisions. New engine fails closed.
"""
import pandas as pd
import pytest

from norisk_quant.strategy import aggregate_bars


def _sample(n=240, start="2024-02-06T00:00:00Z"):
    times = pd.date_range(start, periods=n, freq="min", tz="UTC")
    vals = [2100.0 + (i % 17) * 0.1 for i in range(n)]
    return pd.DataFrame({
        "o": vals,
        "h": [x + 0.2 for x in vals],
        "l": [x - 0.2 for x in vals],
        "c": vals,
    }, index=times)


def test_strict_h4_requires_all_240_source_minutes():
    frame = _sample(240)
    complete = aggregate_bars(frame, "H4")
    assert len(complete) == 1
    assert complete.iloc[0]["close_at"] == pd.Timestamp("2024-02-06T04:00:00Z")
    incomplete = frame.drop(frame.index[100:170])
    assert len(incomplete) == 170
    # Legacy >=170 rule incorrectly passed this bar.
    assert aggregate_bars(incomplete, "H4").empty


def test_strict_h1_requires_all_60_source_minutes():
    frame = _sample(60)
    assert len(aggregate_bars(frame, "H1")) == 1
    assert aggregate_bars(frame.drop(frame.index[12:27]), "H1").empty


def test_opening_partial_60m_candle_is_not_silently_used():
    frame = _sample(240).iloc[15:]
    # Removing first 15 minutes does not make the H4 candle complete.
    assert aggregate_bars(frame, "H4").empty


def test_missing_source_minute_or_bad_alignment_is_rejected():
    frame = _sample(60)
    bad = frame.copy()
    bad.index = bad.index + pd.Timedelta(seconds=30)
    with pytest.raises(ValueError, match="align exactly"):
        aggregate_bars(bad, "H1")
    duplicate = pd.concat([frame, frame.iloc[:1]]).sort_index()
    with pytest.raises(ValueError, match="sorted and unique"):
        aggregate_bars(duplicate, "H1")


def test_source_timestamp_must_have_timezone():
    bad = _sample(60)
    bad.index = bad.index.tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        aggregate_bars(bad, "H1")
