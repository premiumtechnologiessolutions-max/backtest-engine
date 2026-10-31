"""Direct strategy API must reject malformed source M1 before resampling."""
import pandas as pd
import pytest

from norisk_quant.strategy import aggregate_bars


def source():
    index = pd.date_range("2024-01-08T12:00:00Z", periods=15, freq="min")
    return pd.DataFrame({"o": 100., "h": 101., "l": 99., "c": 100.}, index=index)


@pytest.mark.parametrize("column,value", [
    ("o", float("inf")), ("h", -float("inf")), ("c", -1.),
    ("h", 99.9), ("l", 100.1), ("o", True), ("h", "101"),
])
@pytest.mark.parametrize("timeframe", ["M1", "M15"])
def test_bad_direct_ohlc_rejected_before_aggregation(column, value, timeframe):
    frame = source()
    if value is True or isinstance(value, str):
        frame[column] = value
    else:
        frame.loc[frame.index[4], column] = value
    with pytest.raises(ValueError, match="M1 OHLC"):
        aggregate_bars(frame, timeframe)


def test_valid_ohlc_still_aggregates():
    frame = source()
    assert len(aggregate_bars(frame, "M1")) == 15
    out = aggregate_bars(frame, "M15")
    assert len(out) == 1
    assert out.iloc[0]["close_at"] == pd.Timestamp("2024-01-08T12:15:00Z")


def test_empty_source_is_not_fabricated():
    assert aggregate_bars(source().iloc[:0], "M15").empty
