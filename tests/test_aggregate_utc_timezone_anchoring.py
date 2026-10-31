"""Timezone-invariant UTC candle anchoring for direct higher-timeframe callers.

A complete H4 00:00-04:00 UTC block must not disappear or move because
its M1 index was converted to a broker/local timezone for display.
"""
import pandas as pd
import pytest

from norisk_quant.strategy import aggregate_bars


def _source(start_utc: str, *, count: int, timezone: str) -> pd.DataFrame:
    index = pd.date_range(start_utc, periods=count, freq="min").tz_convert(timezone)
    return pd.DataFrame(
        {"o": [2000.0] * count, "h": [2001.0] * count,
         "l": [1999.0] * count, "c": [2000.0] * count},
        index=index,
    )


@pytest.mark.parametrize("start_utc,timezone", [
    ("2024-06-01T00:00:00Z", "America/New_York"),
    ("2024-01-08T00:00:00Z", "America/New_York"),
    ("2024-11-03T04:00:00Z", "America/New_York"),
    ("2024-06-01T00:00:00Z", "Asia/Kolkata"),
])
def test_complete_h4_uses_utc_epoch_boundaries(start_utc, timezone):
    frame = _source(start_utc, count=240, timezone=timezone)
    bars = aggregate_bars(frame, "H4")
    expected = pd.Timestamp(start_utc)
    assert len(bars) == 1
    assert str(bars.index.tz) == "UTC"
    assert bars.index[0] == expected
    assert bars.iloc[0]["close_at"] == expected + pd.Timedelta(hours=4)


@pytest.mark.parametrize("timezone", ["America/New_York", "Asia/Kolkata"])
def test_h1_m15_m1_direct_callers_return_absolute_utc(timezone):
    frame = _source("2024-06-01T00:00:00Z", count=60, timezone=timezone)
    for timeframe, count, step in (("H1", 1, 60), ("M15", 4, 15), ("M1", 60, 1)):
        bars = aggregate_bars(frame, timeframe)
        assert len(bars) == count
        assert str(bars.index.tz) == "UTC"
        assert bars.index[0] == pd.Timestamp("2024-06-01T00:00:00Z")
        assert bars.iloc[0]["close_at"] == bars.index[0] + pd.Timedelta(minutes=step)


def test_subminute_local_timestamps_still_rejected():
    frame = _source("2024-06-01T00:00:00Z", count=240,
                    timezone="America/New_York")
    frame.index = frame.index + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="align exactly"):
        aggregate_bars(frame, "H4")


def test_missing_local_minute_never_fabricates_complete_utc_h4():
    frame = _source("2024-06-01T00:00:00Z", count=240,
                    timezone="America/New_York")
    assert aggregate_bars(frame.drop(frame.index[30]), "H4").empty
