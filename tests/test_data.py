import io
import json
import zipfile

import pandas as pd
import pytest

from norisk_quant.data import import_gold_zip, normalize, quality
from norisk_quant.strategy import aggregate_bars, ema_cross_signals


def source_rows():
    return [
        {"ts": 1577836800, "o": 100, "h": 102, "l": 99, "c": 101,
         "ao": 100.4, "ah": 102.4, "al": 99.4, "ac": 101.4, "v": 1},
        {"ts": 1577836860, "o": 101, "h": 103, "l": 100, "c": 102,
         "ao": 101.4, "ah": 103.4, "al": 100.4, "ac": 102.4, "v": 1},
    ]


def test_original_bid_ask_json_schema():
    df = normalize(pd.DataFrame(source_rows()))
    assert str(df.index.tz) == "UTC"
    assert quality(df)["rows"] == 2
    assert quality(df)["gaps_over_10min"] == 0


def test_duplicate_candles_rejected():
    rows = source_rows()
    rows.append(dict(rows[0]))
    with pytest.raises(ValueError, match="Duplicate"):
        normalize(pd.DataFrame(rows))


def test_invalid_quotes_are_rejected():
    rows = source_rows()
    rows[0]["ah"] = 99
    with pytest.raises(ValueError, match="anomalous"):
        normalize(pd.DataFrame(rows))


def test_import_zip_writes_manifest_and_parquet(tmp_path):
    source = tmp_path / "gold.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("2020.json", json.dumps(source_rows()))
    manifest = import_gold_zip(source, tmp_path / "out")
    assert manifest["annual_partitions"][0]["accepted"]
    assert (tmp_path / "out" / "xauusd_2020.parquet").exists()
    assert (tmp_path / "out" / "manifest.json").exists()


def test_resample_never_uses_missing_minutes_as_full_candle():
    times = pd.date_range("2020-01-01", periods=5, freq="min", tz="UTC")
    raw = pd.DataFrame({"o": [1] * 5, "h": [1] * 5,
                        "l": [1] * 5, "c": [1] * 5}, index=times)
    assert len(aggregate_bars(raw, "M5")) == 1
    assert len(aggregate_bars(raw.drop(times[3]), "M5")) == 0


def test_ema_sample_is_evaluated_after_candle_close():
    times = pd.date_range("2020-01-01", periods=180, freq="min", tz="UTC")
    prices = [100 + i / 30 for i in range(60)] + [
        102 - i / 30 for i in range(60)
    ] + [100 + i / 15 for i in range(60)]
    bars = pd.DataFrame({"o": prices, "h": [x + 0.1 for x in prices],
                         "l": [x - 0.1 for x in prices], "c": prices}, index=times)
    signals = ema_cross_signals(bars, timeframe="M1", fast=4, slow=12)
    assert signals
    assert all(s.confirmed_at > bars.index[0] for s in signals)


def test_import_refuses_mixed_year_and_tracks_member_sha256(tmp_path):
    source = tmp_path / "mixed_year.zip"
    rows = source_rows()
    rows[1]["ts"] = 1609459200  # 2021-01-01 UTC in a 2020 file
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("2020.json", json.dumps(rows))
    manifest = import_gold_zip(source, tmp_path / "out")
    entry = manifest["annual_partitions"][0]
    assert entry["wrong_year_rows"] == 1
    assert entry["accepted"] is False
    assert len(entry["source_member_sha256"]) == 64
    assert not (tmp_path / "out" / "xauusd_2020.parquet").exists()


def test_import_rejects_nonminute_timestamp_and_prevents_stale_overwrite(tmp_path):
    source = tmp_path / "bad_second.zip"
    rows = source_rows()
    rows[1]["ts"] += 1
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("2020.json", json.dumps(rows))
    destination = tmp_path / "out"
    manifest = import_gold_zip(source, destination)
    assert manifest["annual_partitions"][0]["off_minute_timestamps"] == 1
    assert manifest["annual_partitions"][0]["accepted"] is False
    with pytest.raises(FileExistsError, match="versioned"):
        import_gold_zip(source, destination)


def test_import_rejects_duplicate_year_members(tmp_path):
    source = tmp_path / "duplicate_years.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("2020.json", json.dumps(source_rows()))
        archive.writestr("2020 (1).json", json.dumps(source_rows()))
    with pytest.raises(ValueError, match="Multiple source JSON members"):
        import_gold_zip(source, tmp_path / "out")
