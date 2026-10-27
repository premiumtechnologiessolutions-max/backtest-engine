"""Regression: DatetimeIndex.asi8 is not always nanoseconds in Pandas 2.x.

M1 aggregation must accept true minute-aligned UTC timestamps with second,
millisecond, microsecond or nanosecond storage precision. It must still reject
actual subminute offsets rather than silently rounding timestamps.
"""
import pandas as pd
import pytest

from norisk_quant.strategy import aggregate_bars


def _minutes(unit: str) -> pd.DataFrame:
    index = pd.date_range(
        "2024-01-08T12:00:00Z", periods=15, freq="min"
    ).as_unit(unit)
    return pd.DataFrame(
        {"o": [100.0] * 15, "h": [101.0] * 15,
         "l": [99.0] * 15, "c": [100.0] * 15},
        index=index,
    )


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_complete_m15_accepts_all_datetime_storage_units(unit):
    bars = aggregate_bars(_minutes(unit), "M15")
    assert len(bars) == 1
    assert bars.index[0] == pd.Timestamp("2024-01-08T12:00:00Z")
    assert bars.iloc[0]["close_at"] == pd.Timestamp("2024-01-08T12:15:00Z")


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_m1_path_accepts_all_datetime_storage_units(unit):
    bars = aggregate_bars(_minutes(unit), "M1")
    assert len(bars) == 15
    assert bars.iloc[-1]["close_at"] == pd.Timestamp("2024-01-08T12:15:00Z")


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_subminute_offsets_still_fail_closed(unit):
    frame = _minutes(unit)
    frame.index = frame.index + pd.Timedelta(seconds=1)
    with pytest.raises(ValueError, match="align exactly"):
        aggregate_bars(frame, "M15")
