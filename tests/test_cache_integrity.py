"""Imported XAUUSD cache integrity checks; synthetic file bytes only."""
import hashlib
import json

import pytest

from norisk_quant.cache_integrity import read_cache_manifest, verify_cached_partition


def _cache(tmp_path, *, entries=None, payload=b"parquet fixture bytes"):
    (tmp_path / "xauusd_2024.parquet").write_bytes(payload)
    if entries is not None:
        (tmp_path / "manifest.json").write_text(json.dumps({
            "instrument": "XAUUSD", "annual_partitions": entries,
        }))
    return tmp_path


def test_manifest_hash_matches_unmodified_partition(tmp_path):
    content = b"parquet fixture bytes"
    expected = hashlib.sha256(content).hexdigest()
    _cache(tmp_path, entries=[{"year": 2024, "accepted": True, "parquet_sha256": expected}])
    assert verify_cached_partition(tmp_path, 2024, read_cache_manifest(tmp_path)) == "MATCHED_IMPORT_MANIFEST_SHA256"


def test_valid_ohlc_cache_bytes_can_still_be_tampered(tmp_path):
    expected = hashlib.sha256(b"original").hexdigest()
    _cache(tmp_path, entries=[{"year": 2024, "accepted": True, "parquet_sha256": expected}], payload=b"revised")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_cached_partition(tmp_path, 2024, read_cache_manifest(tmp_path))


def test_legacy_manifest_is_not_mislabeled_as_verified(tmp_path):
    _cache(tmp_path, entries=[{"year": 2024, "accepted": True}])
    assert verify_cached_partition(tmp_path, 2024, read_cache_manifest(tmp_path)) == "UNVERIFIED_LEGACY_MANIFEST"


def test_manifestless_cache_is_not_mislabeled_as_verified(tmp_path):
    _cache(tmp_path)
    assert verify_cached_partition(tmp_path, 2024, read_cache_manifest(tmp_path)) == "UNVERIFIED_NO_MANIFEST"


def test_rejected_manifest_partition_cannot_be_loaded(tmp_path):
    _cache(tmp_path, entries=[{"year": 2024, "accepted": False}])
    with pytest.raises(ValueError, match="Unapproved"):
        verify_cached_partition(tmp_path, 2024, read_cache_manifest(tmp_path))


def test_unlisted_partition_cannot_be_loaded(tmp_path):
    _cache(tmp_path, entries=[])
    with pytest.raises(ValueError, match="Unapproved"):
        verify_cached_partition(tmp_path, 2024, read_cache_manifest(tmp_path))


def test_manifest_duplicate_years_fail(tmp_path):
    _cache(tmp_path, entries=[{"year": 2024, "accepted": True}, {"year": 2024, "accepted": True}])
    with pytest.raises(ValueError, match="Duplicate"):
        read_cache_manifest(tmp_path)


@pytest.mark.parametrize("bad_digest", ["abc", "Z" * 64, 5, False, "0" * 65])
def test_invalid_manifest_digest_fails(tmp_path, bad_digest):
    _cache(tmp_path, entries=[{"year": 2024, "accepted": True, "parquet_sha256": bad_digest}])
    with pytest.raises(ValueError, match="Invalid XAUUSD cache SHA-256"):
        verify_cached_partition(tmp_path, 2024, read_cache_manifest(tmp_path))


def test_missing_partition_fails(tmp_path):
    with pytest.raises(ValueError, match="Missing XAUUSD"):
        verify_cached_partition(tmp_path, 2024, None)


def test_malformed_manifest_fails(tmp_path):
    _cache(tmp_path)
    (tmp_path / "manifest.json").write_text("{oops")
    with pytest.raises(ValueError, match="Invalid XAUUSD cache manifest"):
        read_cache_manifest(tmp_path)


def test_manifest_wrong_instrument_fails(tmp_path):
    _cache(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"instrument": "EURUSD", "annual_partitions": []}))
    with pytest.raises(ValueError, match="Invalid XAUUSD cache manifest"):
        read_cache_manifest(tmp_path)


@pytest.mark.parametrize("missing_field", ["parquet_sha256", "loaded_m1_bidask_sha256"])
def test_version2_manifest_cannot_silently_drop_a_digest(tmp_path, missing_field):
    digests = {"parquet_sha256": "a" * 64, "loaded_m1_bidask_sha256": "b" * 64}
    digests.pop(missing_field)
    _cache(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({
        "format_version": 2, "instrument": "XAUUSD",
        "annual_partitions": [{"year": 2024, "accepted": True, **digests}],
    }))
    with pytest.raises(ValueError, match="version-2 XAUUSD cache digest"):
        read_cache_manifest(tmp_path)


@pytest.mark.parametrize("version", [0, 3, True, "2"])
def test_unsupported_or_invalid_manifest_version_rejected(tmp_path, version):
    _cache(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({
        "format_version": version, "instrument": "XAUUSD",
        "annual_partitions": [],
    }))
    with pytest.raises(ValueError, match="Unsupported XAUUSD cache manifest version"):
        read_cache_manifest(tmp_path)


def test_version2_rejected_partition_needs_no_hashes(tmp_path):
    _cache(tmp_path, entries=[{"year": 2024, "accepted": False}])
    (tmp_path / "manifest.json").write_text(json.dumps({
        "format_version": 2, "instrument": "XAUUSD",
        "annual_partitions": [{"year": 2024, "accepted": False}],
    }))
    assert read_cache_manifest(tmp_path)[2024]["accepted"] is False
