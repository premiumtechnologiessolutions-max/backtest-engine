"""Regression: an inclusive Dec 31 date must not inspect the next calendar year.

Synthetic M1 quotes and fake Parquet bytes only. No private gold data,
pyarrow dependency, broker fills, or trading-performance assumptions.
"""
import hashlib
import json
import zipfile

import pandas as pd
import pytest

from norisk_quant.data import fingerprint_loaded_m1, load_market, normalize


def _row(date):
    return {
        "ts": int(pd.Timestamp(date).timestamp()),
        "o": 2000.0, "h": 2001.0, "l": 1999.0, "c": 2000.5,
        "ao": 2000.4, "ah": 2001.4, "al": 1999.4, "ac": 2000.9,
    }


def test_dec31_does_not_require_next_year_accepted_partition(tmp_path, monkeypatch):
    directory = tmp_path / "cache"
    directory.mkdir()
    raw = normalize(pd.DataFrame([_row("2024-12-31T23:59:00Z")]))
    content = b"synthetic parquet fixture"
    (directory / "xauusd_2024.parquet").write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    manifest = {
        "format_version": 2, "instrument": "XAUUSD",
        "annual_partitions": [
            {"year": 2024, "accepted": True, "rows": 1,
             "parquet_sha256": sha,
             "loaded_m1_bidask_sha256": fingerprint_loaded_m1(raw)},
            # This year is accepted in metadata but its file is absent.
            # It must not block a query ending 2024-12-31.
            {"year": 2025, "accepted": True, "rows": 1,
             "parquet_sha256": "a" * 64,
             "loaded_m1_bidask_sha256": "b" * 64},
        ],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    reads = []

    def fake_read_parquet(path):
        reads.append(path.name)
        assert path.name == "xauusd_2024.parquet"
        return raw.copy()

    monkeypatch.setattr(pd, "read_parquet", fake_read_parquet)
    result = load_market(directory, "2024-01-01", "2024-12-31")
    assert len(result) == 1
    assert reads == ["xauusd_2024.parquet"]
    assert result.attrs["cache_integrity"] == "MATCHED_IMPORT_MANIFEST_SHA256"


def test_dec31_manifestless_cache_does_not_claim_partial_year(tmp_path, monkeypatch):
    directory = tmp_path / "cache"
    directory.mkdir()
    (directory / "xauusd_2024.parquet").write_bytes(b"synthetic fixture")
    raw = normalize(pd.DataFrame([_row("2024-12-31T23:59:00Z")]))
    monkeypatch.setattr(pd, "read_parquet", lambda _: raw.copy())
    result = load_market(directory, "2024-01-01", "2024-12-31")
    assert result.attrs["cache_integrity"] == "UNVERIFIED_LEGACY_OR_NO_MANIFEST"


def test_dec31_zip_ignores_duplicate_members_from_unrequested_next_year(tmp_path):
    archive = tmp_path / "synthetic.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("2024.json", json.dumps([_row("2024-12-31T23:59:00Z")]))
        handle.writestr("2025.json", json.dumps([_row("2025-01-01T00:00:00Z")]))
        handle.writestr("2025 (1).json", json.dumps([_row("2025-01-01T00:00:00Z")]))
    result = load_market(archive, "2024-01-01", "2024-12-31")
    assert len(result) == 1
    assert result.index.max() == pd.Timestamp("2024-12-31T23:59:00Z")


def test_reversed_date_range_fails_before_reading(tmp_path):
    with pytest.raises(ValueError, match="End date must not precede start date"):
        load_market(tmp_path / "does-not-exist.zip", "2025-01-02", "2024-12-31")


def test_cross_year_zip_still_includes_next_year_when_explicitly_requested(tmp_path):
    archive = tmp_path / "synthetic_two_years.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("2024.json", json.dumps([_row("2024-12-31T23:59:00Z")]))
        handle.writestr("2025.json", json.dumps([_row("2025-01-01T00:00:00Z")]))
    result = load_market(archive, "2024-12-31", "2025-01-01")
    assert len(result) == 2
    assert result.index.year.tolist() == [2024, 2025]
