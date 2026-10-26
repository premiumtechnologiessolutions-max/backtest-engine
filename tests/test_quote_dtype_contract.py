"""Synthetic regressions: quote dtype coercion must not launder cached M1."""
import pandas as pd
import pytest

from norisk_quant.data import (
    fingerprint_loaded_m1, normalize, read_source, validate_loaded_m1,
)


def _raw():
    return pd.DataFrame([
        {"ts": 1704153600, "o": 2000.0, "h": 2001.0, "l": 1999.0,
         "c": 2000.5, "ao": 2000.4, "ah": 2001.4, "al": 1999.4,
         "ac": 2000.9},
    ])


@pytest.mark.parametrize("column", ["o", "h", "l", "c", "ao", "ah", "al", "ac"])
def test_raw_boolean_price_rejected_before_backtest(column):
    raw = _raw()
    raw[column] = True
    with pytest.raises(ValueError, match="Source M1 requires numeric non-boolean"):
        normalize(raw)


@pytest.mark.parametrize("value", ["2000.9", True])
def test_cached_price_schema_rejects_text_or_boolean(value):
    frame = normalize(_raw())
    frame["ac"] = pd.Series([value], index=frame.index)
    with pytest.raises(ValueError, match="Loaded M1 requires numeric non-boolean"):
        validate_loaded_m1(frame)


@pytest.mark.parametrize("value", ["2000.9", True])
def test_fingerprint_rejects_coerced_quote_types(value):
    frame = normalize(_raw())
    frame["ac"] = pd.Series([value], index=frame.index)
    with pytest.raises(ValueError, match="Fingerprint M1 requires numeric non-boolean"):
        fingerprint_loaded_m1(frame)


@pytest.mark.parametrize("value", ["2000.9", True])
def test_direct_parquet_rejects_malformed_quote_dtype(monkeypatch, value):
    frame = normalize(_raw())
    frame["ac"] = pd.Series([value], index=frame.index)
    monkeypatch.setattr(pd, "read_parquet", lambda _: frame)
    with pytest.raises(ValueError, match="Loaded M1 requires numeric non-boolean"):
        read_source("synthetic.parquet")


def test_numeric_json_text_remains_normalizable_for_csv_compatibility():
    raw = _raw()
    raw["ac"] = "2000.9"
    clean = normalize(raw)
    assert clean["ac"].iloc[0] == pytest.approx(2000.9)
    assert len(fingerprint_loaded_m1(clean)) == 64
    assert validate_loaded_m1(clean) is clean
