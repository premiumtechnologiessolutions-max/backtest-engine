"""Fail-closed regressions for source M1 quote and timestamp integrity."""
import json
import zipfile

import pandas as pd
import pytest

from norisk_quant.data import import_gold_zip, load_market, normalize, quality


def _rows():
    return [
        {"ts": 1577836800, "o": 100.0, "h": 102.0, "l": 99.0, "c": 101.0,
         "ao": 100.4, "ah": 102.4, "al": 99.4, "ac": 101.4},
        {"ts": 1577836860, "o": 101.0, "h": 103.0, "l": 100.0, "c": 102.0,
         "ao": 101.4, "ah": 103.4, "al": 100.4, "ac": 102.4},
    ]


@pytest.mark.parametrize("field,value", [
    ("h", float("nan")), ("ac", float("inf")), ("o", 0.0),
    ("al", -1.0), ("ah", 101.9), ("al", 98.9),
])
def test_strict_normalize_rejects_invalid_quotes(field, value):
    rows = _rows()
    rows[0][field] = value
    with pytest.raises(ValueError, match="anomalous"):
        normalize(pd.DataFrame(rows))


def test_strict_normalize_rejects_off_minute_timestamp():
    rows = _rows()
    rows[0]["ts"] += 1
    with pytest.raises(ValueError, match="anomalous"):
        normalize(pd.DataFrame(rows))


def test_quality_counts_nonfinite_and_crossed_low_quotes():
    rows = _rows()
    rows[0]["al"] = 98.9
    rows[1]["ah"] = float("inf")
    audit = quality(normalize(pd.DataFrame(rows), strict=False))
    assert audit["ask_below_bid_low"] == 1
    assert audit["nonfinite_price_rows"] == 1


@pytest.mark.parametrize("field,value,check", [
    ("ah", None, "nonfinite_price_rows"),
    ("al", "Infinity", "nonfinite_price_rows"),
    ("o", 0, "nonpositive_price_rows"),
    ("al", 98.9, "ask_below_bid_low"),
])
def test_zip_import_quarantines_bad_quotes_without_parquet(tmp_path, field, value, check):
    rows = _rows()
    rows[0][field] = value
    archive = tmp_path / "gold.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("2020.json", json.dumps(rows))
    output = tmp_path / "import"
    manifest = import_gold_zip(archive, output)
    entry = manifest["annual_partitions"][0]
    assert entry[check] >= 1
    assert entry["accepted"] is False
    assert not (output / "xauusd_2020.parquet").exists()


def test_direct_zip_load_refuses_nonfinite_quotes(tmp_path):
    rows = _rows()
    rows[0]["ao"] = None
    archive = tmp_path / "gold.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("2020.json", json.dumps(rows))
    with pytest.raises(ValueError, match="anomalous"):
        load_market(archive, "2020-01-01", "2020-01-31")


@pytest.mark.parametrize("field,value", [
    ("ah", 101.9), ("al", 98.9), ("ac", float("nan")), ("o", 0.0),
])
def test_cached_parquet_quote_tampering_is_rejected(tmp_path, field, value):
    # Parquet must not bypass the strict JSON/ZIP source gates.
    frame = normalize(pd.DataFrame(_rows()))
    frame.loc[frame.index[0], field] = value
    cached = tmp_path / "cached.parquet"
    frame.to_parquet(cached)
    with pytest.raises(ValueError, match="Loaded M1"):
        load_market(cached, "2020-01-01", "2020-01-31")


def test_cached_parquet_rejects_non_utc_and_off_minute_index(tmp_path):
    frame = normalize(pd.DataFrame(_rows()))
    cached = tmp_path / "cached.parquet"
    frame.index = frame.index + pd.Timedelta(seconds=1)
    frame.to_parquet(cached)
    with pytest.raises(ValueError, match="minute opens"):
        load_market(cached, "2020-01-01", "2020-01-31")


def test_valid_cached_parquet_remains_loadable(tmp_path):
    frame = normalize(pd.DataFrame(_rows()))
    cached = tmp_path / "cached.parquet"
    frame.to_parquet(cached)
    loaded = load_market(cached, "2020-01-01", "2020-01-31")
    pd.testing.assert_frame_equal(loaded, frame)
