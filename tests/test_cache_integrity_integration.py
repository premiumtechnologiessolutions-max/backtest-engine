"""Synthetic ZIP + mocked Parquet IO; no raw market data or pyarrow required."""
import json
import zipfile

import pandas as pd
import pytest

from norisk_quant.data import import_gold_zip, load_market, normalize


def _rows():
    return [
        {"ts": 1704153600, "o": 2000.0, "h": 2001.0, "l": 1999.0, "c": 2000.5,
         "ao": 2000.4, "ah": 2001.4, "al": 1999.4, "ac": 2000.9, "v": 1},
        {"ts": 1704153660, "o": 2000.5, "h": 2002.0, "l": 2000.0, "c": 2001.0,
         "ao": 2000.9, "ah": 2002.4, "al": 2000.4, "ac": 2001.4, "v": 1},
    ]


def _import_fixture(tmp_path, monkeypatch):
    source = tmp_path / "private_synthetic.zip"
    with zipfile.ZipFile(source, "w") as handle:
        handle.writestr("2024.json", json.dumps(_rows()))
    monkeypatch.setattr(pd.DataFrame, "to_parquet",
                        lambda self, path, **kwargs: path.write_bytes(b"fixture-parquet-bytes"))
    dest = tmp_path / "cache"
    manifest = import_gold_zip(source, dest)
    monkeypatch.setattr(pd, "read_parquet", lambda path: normalize(pd.DataFrame(_rows())))
    return dest, manifest


def test_new_import_records_two_digests_and_loads_verified(tmp_path, monkeypatch):
    dest, manifest = _import_fixture(tmp_path, monkeypatch)
    entry = manifest["annual_partitions"][0]
    assert manifest["format_version"] == 2
    assert len(entry["parquet_sha256"]) == 64
    assert len(entry["loaded_m1_bidask_sha256"]) == 64
    loaded = load_market(dest, "2024-01-01", "2024-01-31")
    assert len(loaded) == 2
    assert loaded.attrs["cache_integrity"] == "MATCHED_IMPORT_MANIFEST_SHA256"


def test_tampered_cache_bytes_rejected_even_when_quotes_still_valid(tmp_path, monkeypatch):
    dest, _ = _import_fixture(tmp_path, monkeypatch)
    (dest / "xauusd_2024.parquet").write_bytes(b"altered-valid-looking-parquet")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        load_market(dest, "2024-01-01", "2024-01-31")


def test_changed_m1_quotes_detected_even_when_mocked_bytes_match(tmp_path, monkeypatch):
    dest, _ = _import_fixture(tmp_path, monkeypatch)
    revised = normalize(pd.DataFrame(_rows()))
    revised.loc[revised.index[0], "ac"] += 0.01
    monkeypatch.setattr(pd, "read_parquet", lambda path: revised)
    with pytest.raises(ValueError, match="BID/ASK fingerprint mismatch"):
        load_market(dest, "2024-01-01", "2024-01-31")


def test_missing_accepted_partition_rejected(tmp_path, monkeypatch):
    dest, _ = _import_fixture(tmp_path, monkeypatch)
    (dest / "xauusd_2024.parquet").unlink()
    with pytest.raises(ValueError, match="accepted XAUUSD|Accepted XAUUSD"):
        load_market(dest, "2024-01-01", "2024-01-31")


def test_legacy_cache_is_loadable_but_explicitly_unverified(tmp_path, monkeypatch):
    dest, manifest = _import_fixture(tmp_path, monkeypatch)
    # Genuine v1 manifests predate both hashes; removing them from v2 is
    # corruption, not a legitimate reason to claim a legacy cache.
    manifest["format_version"] = 1
    entry = manifest["annual_partitions"][0]
    entry.pop("parquet_sha256")
    entry.pop("loaded_m1_bidask_sha256")
    (dest / "manifest.json").write_text(json.dumps(manifest))
    loaded = load_market(dest, "2024-01-01", "2024-01-31")
    assert loaded.attrs["cache_integrity"] == "UNVERIFIED_LEGACY_OR_NO_MANIFEST"


def test_manifestless_cache_is_loadable_but_explicitly_unverified(tmp_path, monkeypatch):
    dest, _ = _import_fixture(tmp_path, monkeypatch)
    (dest / "manifest.json").unlink()
    loaded = load_market(dest, "2024-01-01", "2024-01-31")
    assert loaded.attrs["cache_integrity"] == "UNVERIFIED_LEGACY_OR_NO_MANIFEST"


def test_missing_requested_year_fails_closed_even_when_other_partition_verified(tmp_path, monkeypatch):
    dest, _ = _import_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match=r"Missing requested Parquet source years: \\[2023\\]"):
        load_market(dest, "2023-01-01", "2024-01-31")


def test_manifestless_cache_cannot_silently_truncate_requested_years(tmp_path, monkeypatch):
    dest, _ = _import_fixture(tmp_path, monkeypatch)
    (dest / "manifest.json").unlink()
    with pytest.raises(ValueError, match=r"Missing requested Parquet source years: \\[2023\\]"):
        load_market(dest, "2023-01-01", "2024-01-31")


def test_single_year_cache_does_not_require_unrequested_adjacent_year(tmp_path, monkeypatch):
    dest, _ = _import_fixture(tmp_path, monkeypatch)
    result = load_market(dest, "2024-01-01", "2024-12-31")
    assert len(result) == 2
    assert result.attrs["cache_integrity"] == "MATCHED_IMPORT_MANIFEST_SHA256"


@pytest.mark.parametrize("missing_field", ["parquet_sha256", "loaded_m1_bidask_sha256"])
def test_version2_digest_downgrade_rejected_before_parquet_read(tmp_path, monkeypatch, missing_field):
    dest, manifest = _import_fixture(tmp_path, monkeypatch)
    manifest["annual_partitions"][0].pop(missing_field)
    (dest / "manifest.json").write_text(json.dumps(manifest))
    def forbidden_read(path):
        raise AssertionError("Must reject damaged manifest before opening Parquet")
    monkeypatch.setattr(pd, "read_parquet", forbidden_read)
    with pytest.raises(ValueError, match="version-2 XAUUSD cache digest"):
        load_market(dest, "2024-01-01", "2024-01-31")
