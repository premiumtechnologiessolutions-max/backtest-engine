"""Synthetic regressions: malformed tick events must not certify real provenance."""
import numpy as np
import pandas as pd
import pytest

from norisk_quant.ticks import TickSource, normalize_ticks


def _ticks():
    return pd.DataFrame({
        "ts_utc": ["2024-01-02T00:00:00Z", "2024-01-02T00:00:00Z",
                   "2024-01-02T00:00:01Z"],
        "bid": [100.0, 100.1, 100.2],
        "ask": [100.4, 100.5, 100.6],
        "seq": [1, 2, 1],
    })


def _source():
    return TickSource(provider="synthetic regression source", symbol="XAUUSD")


@pytest.mark.parametrize("column", ["bid", "ask", "seq"])
@pytest.mark.parametrize("value", [True, np.bool_(False)])
def test_tick_ingest_rejects_boolean_cells_before_numeric_coercion(column, value):
    frame = _ticks()
    frame[column] = frame[column].astype(object)
    frame.at[0, column] = value
    with pytest.raises(ValueError, match="cannot contain boolean"):
        normalize_ticks(frame, _source())


@pytest.mark.parametrize("sequence", [float("inf"), float("-inf"), 2**53, -(2**53)])
def test_tick_ingest_rejects_unsafe_duplicate_sequence(sequence):
    frame = _ticks()
    frame["seq"] = frame["seq"].astype(object)
    frame.at[1, "seq"] = sequence
    with pytest.raises(ValueError, match="safely representable"):
        normalize_ticks(frame, _source())


def test_tick_ingest_accepts_csv_numeric_text_sequence_and_quotes():
    frame = _ticks()
    for col in ("bid", "ask", "seq"):
        frame[col] = frame[col].astype(str)
    normalized = normalize_ticks(frame, _source())
    assert len(normalized) == 3
    assert normalized.index.is_monotonic_increasing
    assert normalized["seq"].iloc[:2].tolist() == [1, 2]


def test_tick_ingest_rejects_missing_duplicate_sequence():
    frame = _ticks()
    frame.at[0, "seq"] = np.nan
    with pytest.raises(ValueError, match="non-null sequence"):
        normalize_ticks(frame, _source())
