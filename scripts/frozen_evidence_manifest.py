"""Fail-closed SHA256 inventory for locally published frozen annual evidence.

The inventory contains filenames, sizes and digests only. It does not certify
broker fills, research independence, or the identity of private market data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

SCHEMA = "norisk-frozen-evidence-sha256-v1"
MANIFEST_NAME = "evidence_manifest.json"
ANNUAL_FILES = frozenset({
    "summary.json", "trades.csv", "monthly.csv", "weekly.csv",
    "equity_m1.csv", "gap_catalogue.csv",
})
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_identity(years: list[int], source_sha: str) -> None:
    if (type(years) is not list or not years
            or any(type(year) is not int or not 2010 <= year <= 2026 for year in years)
            or len(years) != len(set(years))):
        raise ValueError("Evidence manifest requires distinct integer source years")
    if type(source_sha) is not str or SHA256_PATTERN.fullmatch(source_sha) is None:
        raise ValueError("Evidence manifest requires lowercase source SHA256")


def _scan(root: Path) -> dict[str, dict[str, str | int]]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Evidence root must be a real directory")
    files: dict[str, dict[str, str | int]] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Evidence tree must not contain symlinks")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("Evidence tree contains a nonregular file")
        relative = path.relative_to(root).as_posix()
        if relative == MANIFEST_NAME:
            continue
        files[relative] = {"path": relative, "bytes": path.stat().st_size,
                           "sha256": _sha256(path)}
    return files


def _required(years: list[int]) -> set[str]:
    return {"frozen_sensitivity_summary.json"} | {
        f"{year}/{filename}" for year in years for filename in ANNUAL_FILES
    }


def _validate_inventory(files: dict[str, dict[str, str | int]], years: list[int]) -> None:
    missing = _required(years) - files.keys()
    if missing:
        raise ValueError(f"Evidence inventory missing required reports: {sorted(missing)}")


def write_evidence_manifest(root: Path, years: list[int], source_sha: str) -> dict:
    """Write inventory only after all annual source/accounting audits pass."""
    root = Path(root)
    _validate_identity(years, source_sha)
    if (root / MANIFEST_NAME).exists() or (root / MANIFEST_NAME).is_symlink():
        raise FileExistsError("Evidence manifest already exists")
    files = _scan(root)
    _validate_inventory(files, years)
    payload = {
        "schema": SCHEMA,
        "source_archive_sha256": source_sha,
        "years": list(years),
        "files": [files[name] for name in sorted(files)],
    }
    (root / MANIFEST_NAME).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    verify_evidence_manifest(root, expected_years=years, expected_source_sha=source_sha)
    return payload


def verify_evidence_manifest(
    root: Path, *, expected_years: list[int] | None = None,
    expected_source_sha: str | None = None,
) -> dict:
    """Rehash all evidence, rejecting missing, extra, changed or linked files."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Evidence root must be a real directory")
    manifest = root / MANIFEST_NAME
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Evidence manifest missing or symlinked")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if type(payload) is not dict or set(payload) != {
        "schema", "source_archive_sha256", "years", "files"
    } or payload["schema"] != SCHEMA:
        raise ValueError("Evidence manifest schema mismatch")
    years, source_sha = payload["years"], payload["source_archive_sha256"]
    _validate_identity(years, source_sha)
    if expected_years is not None and years != expected_years:
        raise ValueError("Evidence manifest selected years mismatch")
    if expected_source_sha is not None and source_sha != expected_source_sha:
        raise ValueError("Evidence manifest source identity mismatch")
    records = payload["files"]
    if type(records) is not list:
        raise ValueError("Evidence manifest files must be a list")
    listed: dict[str, dict] = {}
    for record in records:
        if type(record) is not dict or set(record) != {"path", "bytes", "sha256"}:
            raise ValueError("Evidence manifest record schema mismatch")
        name, size, digest = record["path"], record["bytes"], record["sha256"]
        if (type(name) is not str or not name or "\\" in name
                or PurePosixPath(name).is_absolute()
                or any(part in ("", ".", "..") for part in name.split("/"))
                or name == MANIFEST_NAME):
            raise ValueError("Evidence manifest contains unsafe path")
        if (type(size) is not int or size < 0 or type(digest) is not str
                or SHA256_PATTERN.fullmatch(digest) is None or name in listed):
            raise ValueError("Evidence manifest contains invalid or duplicate record")
        listed[name] = record
    if list(listed) != sorted(listed):
        raise ValueError("Evidence manifest inventory is not canonical sorted order")
    observed = _scan(root)
    _validate_inventory(observed, years)
    if set(observed) != set(listed):
        raise ValueError("Evidence manifest file inventory differs from disk")
    for name, recorded in listed.items():
        if observed[name] != recorded:
            raise ValueError(f"Evidence file changed after publication: {name}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a frozen private annual evidence directory")
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    result = verify_evidence_manifest(args.root)
    print(f"Verified {len(result['files'])} evidence files for {result['years']}")


if __name__ == "__main__":
    main()
