"""Fail-closed file integrity checks for imported XAUUSD Parquet partitions.

A digest in an editable manifest proves consistency with that manifest, NOT
provider authenticity. Legacy manifests are explicitly classified unverified.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_cache_manifest(directory: Path) -> dict[int, dict] | None:
    """Validate metadata before trusting a cached partition filename."""
    path = directory / "manifest.json"
    if not path.exists():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid XAUUSD cache manifest") from exc
    if (not isinstance(document, dict) or document.get("instrument") != "XAUUSD"
            or not isinstance(document.get("annual_partitions"), list)):
        raise ValueError("Invalid XAUUSD cache manifest structure")
    # Version-2 imports promise BOTH file-byte and semantic quote digests.
    # Never silently downgrade a damaged v2 manifest into legacy/unverified.
    # Version 1 (or absent version) remains loadable but is marked unverified.
    version = document.get("format_version", 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError("Unsupported XAUUSD cache manifest version")
    entries = {}
    for item in document["annual_partitions"]:
        if (not isinstance(item, dict) or type(item.get("year")) is not int
                or not 2000 <= item["year"] <= 2100
                or type(item.get("accepted")) is not bool):
            raise ValueError("Invalid XAUUSD cache partition entry")
        year = item["year"]
        if year in entries:
            raise ValueError("Duplicate XAUUSD cache manifest year")
        if version == 2 and item["accepted"]:
            for field in ("parquet_sha256", "loaded_m1_bidask_sha256"):
                digest = item.get(field)
                if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                    raise ValueError(
                        f"Missing or invalid version-2 XAUUSD cache digest {field} for {year}"
                    )
        entries[year] = item
    return entries


def verify_cached_partition(directory: Path, year: int,
                            entries: dict[int, dict] | None) -> str:
    """Check imported Parquet bytes against recorded digest, if available.

    Missing/legacy manifest provenance is explicitly UNVERIFIED; no attempt is
    made to silently bless a legacy cache with a newly calculated digest.
    """
    path = directory / f"xauusd_{year}.parquet"
    if not path.is_file():
        raise ValueError(f"Missing XAUUSD cache partition {year}")
    if entries is None:
        return "UNVERIFIED_NO_MANIFEST"
    entry = entries.get(year)
    if entry is None or entry.get("accepted") is not True:
        raise ValueError(f"Unapproved XAUUSD cache partition {year}")
    expected = entry.get("parquet_sha256")
    if expected is None:
        return "UNVERIFIED_LEGACY_MANIFEST"
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise ValueError(f"Invalid XAUUSD cache SHA-256 for {year}")
    if file_sha256(path) != expected:
        raise ValueError(f"XAUUSD cache SHA-256 mismatch for {year}; quarantine modified Parquet")
    return "MATCHED_IMPORT_MANIFEST_SHA256"
