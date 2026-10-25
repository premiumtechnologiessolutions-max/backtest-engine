"""Direct Parquet reads must enforce the same M1 quote integrity as load_market.

The Parquet reader is monkeypatched to exercise the public ingress contract
without needing a market-data archive or a physical Parquet fixture.
These tests do NOT substitute for installed-package/pyarrow integration tests.
"""
import numpy as np
import pandas as pd
import pytest

from norisk_quant.data import read_source


def _valid_m1():
    return pd.DataFrame(
        [{
            "o": 100.0, "h": 102.0, "l": 99.0, "c": 101.0,
            "ao": 100.4, "ah": 102.4, "al": 99.4, "ac": 101.4,
        }],
        index=pd.date_range("2024-01-02T00:00:00Z", periods=1, freq="min"),
    )


def test_direct_parquet_read_accepts_valid_m1(monkeypatch):
    frame = _valid_m1()
    monkeypatch.setattr(pd, "read_parquet", lambda path: frame)
    assert read_source("fixture.parquet") is frame


@pytest.mark.parametrize("mutation", [
    "missing_ask", "crossed_ask_high", "off_minute",
    "non_utc", "duplicate_minute", "zero_bid",
])
def test_direct_parquet_read_quarantines_invalid_m1(monkeypatch, mutation):
    frame = _valid_m1()
    if mutation == "missing_ask":
        frame.loc[frame.index[0], "ao"] = np.nan
    elif mutation == "crossed_ask_high":
        frame.loc[frame.index[0], "ah"] = 101.0
    elif mutation == "off_minute":
        frame.index = frame.index + pd.Timedelta(seconds=1)
    elif mutation == "non_utc":
        frame.index = frame.index.tz_convert("Europe/Paris")
    elif mutation == "duplicate_minute":
        frame = pd.concat([frame, frame])
    elif mutation == "zero_bid":
        frame.loc[frame.index[0], "o"] = 0.0
    monkeypatch.setattr(pd, "read_parquet", lambda path: frame)
    with pytest.raises(ValueError, match="Loaded M1"):
        read_source("fixture.parquet")
