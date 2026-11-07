"""Lossless, optional cold storage of already-audited M1 equity CSV ledgers.

No raw quote/ledger is uploaded. Archive is *reversible*: restore verifies
original SHA256 and size. Pruning raw copies requires an explicit flag;
normal mode NEVER removes originals. Do not confuse compression with audit.
"""
from __future__ import annotations

import argparse
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

from scripts.materialize_arithmetic_generation import (
    _encoded, _load_strict, _publish_once,
)
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA

SCHEMA = "NRFX_EQUITY_COLD_STORAGE_V1"
EQUITY_FILE = "equity_m1.csv"
MAX_CSV_BYTES = 2 * 1024 ** 3


def _safe(path: Path, root: Path) -> Path:
    path, root = Path(path), Path(root)
    if (path.is_symlink() or not path.resolve().is_relative_to(root.resolve())
            or any(x.is_symlink() for x in (root, *path.parents))):
        raise ValueError("Unsafe equity evidence path or symlink")
    return path


def _generation_root(folder: Path) -> Path:
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Cold storage requires an existing generation directory")
    next_input = folder / "next_training_input.json"
    proof_file = folder / "next_training_input.json.evidence.json"
    if next_input.is_symlink() or proof_file.is_symlink():
        raise ValueError("Unsafe verified generation input")
    training, digest = _load_strict(next_input)
    proof, _ = _load_strict(proof_file)
    if (type(training) is not dict or type(proof) is not dict
            or training.get("schema") != "NRFX_ARITHMETIC_TRAINING_INPUT_V1"
            or proof.get("schema") != "NRFX_ARITHMETIC_FEEDBACK_EVIDENCE_V1"
            or proof.get("next_input_sha256") != digest
            or proof.get("original_archive_sha256") != SOURCE_SHA
            or proof.get("training_only") is not True
            or proof.get("independent_oos_proven") is not False
            or proof.get("live_trading_authorized") is not False):
        raise ValueError("Complete audited training generation required")
    return folder


def _paths(root: Path):
    files = []
    shards = sorted(root.glob("replay_*"))
    if not shards:
        raise ValueError("No annual replay shards found")
    for shard in shards:
        _safe(shard, root)
        index, _ = _load_strict(shard / "training_replay_index.json")
        if (type(index) is not dict or index.get("training_only") is not True
                or index.get("independent_oos_proven") is not False
                or type(index.get("results")) is not list):
            raise ValueError("Unsafe annual shard provenance")
        for row in index["results"]:
            if type(row) is not dict or type(row.get("relative_dir")) is not str:
                raise ValueError("Missing formula evidence directory")
            name = row["relative_dir"]
            if name in (".", "..") or "/" in name or "\\" in name:
                raise ValueError("Unsafe annual formula path")
            for engine in ("reference", "fast"):
                relative = shard / name / engine / EQUITY_FILE
                _safe(relative, root)
                files.append(relative)
    if len(set(files)) != len(files):
        raise ValueError("Duplicate equity evidence file")
    return files


def _digest(path: Path) -> tuple[str, int]:
    h = sha256()
    total = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            if total > MAX_CSV_BYTES:
                raise ValueError("Equity evidence exceeds per-file budget")
            h.update(chunk)
    return h.hexdigest(), total


def _verify_archive(archive: Path, expected_sha: str, expected_size: int) -> None:
    h, total = sha256(), 0
    with gzip.open(archive, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            if total > MAX_CSV_BYTES:
                raise ValueError("Archive expansion exceeds equity file budget")
            h.update(chunk)
    if h.hexdigest() != expected_sha or total != expected_size:
        raise ValueError("Compressed equity archive failed lossless SHA verification")


def freeze_equity_storage(folder: Path, *, prune_raw: bool = False) -> dict:
    """Create verified deterministic gzip mirrors; opt-in prune only."""
    if type(prune_raw) is not bool:
        raise ValueError("Prune raw must be an explicit boolean")
    root = _generation_root(folder)
    paths = _paths(root)
    records = []
    for path in paths:
        if not path.is_file():
            raise ValueError("Original equity ledger required to create cold storage")
        digest, size = _digest(path)
        gz = path.with_name(EQUITY_FILE + ".gz")
        _safe(gz, root)
        if not gz.exists():
            fd, temp = tempfile.mkstemp(prefix=".nrfx_equity_", dir=gz.parent)
            try:
                with os.fdopen(fd, "wb") as out, path.open("rb") as src:
                    with gzip.GzipFile(fileobj=out, mode="wb",
                                       filename="", mtime=0,
                                       compresslevel=1) as zipped:
                        shutil.copyfileobj(src, zipped, length=1024*1024)
                    out.flush()
                    os.fsync(out.fileno())
                try:
                    os.link(temp, gz)
                except FileExistsError:
                    pass
            finally:
                Path(temp).unlink(missing_ok=True)
        if gz.is_symlink() or not gz.is_file():
            raise ValueError("Unsafe compressed equity evidence")
        _verify_archive(gz, digest, size)
        zipped_sha, zipped_size = _digest(gz)
        records.append({"file": str(path.relative_to(root).as_posix()),
                        "sha256": digest, "original_bytes": size,
                        "archive_sha256": zipped_sha,
                        "archive_bytes": zipped_size})
    manifest = {"schema": SCHEMA, "generation": root.name,
                "training_only": True, "independent_oos_proven": False,
                "live_trading_authorized": False, "equity_files": records}
    _publish_once(root / "equity_cold_storage.json", _encoded(manifest))
    if prune_raw:
        # This pass runs only after EVERY archive passes decompression
        # verification and the immutable manifest is safely published.
        for path in paths:
            if path.is_symlink():
                raise ValueError("Unsafe raw evidence before prune")
            path.unlink()
    return {"file_count": len(records),
            "original_bytes": sum(x["original_bytes"] for x in records),
            "compressed_bytes": sum(x["archive_bytes"] for x in records),
            "raw_pruned": prune_raw, "independent_oos_proven": False}


def restore_equity_storage(folder: Path) -> dict:
    """Verify immutable manifest and rehydrate missing CSVs for full audits."""
    root = _generation_root(folder)
    manifest, _ = _load_strict(root / "equity_cold_storage.json")
    if (type(manifest) is not dict or manifest.get("schema") != SCHEMA
            or manifest.get("generation") != root.name
            or manifest.get("independent_oos_proven") is not False
            or type(manifest.get("equity_files")) is not list):
        raise ValueError("Invalid immutable equity archive manifest")
    expected = {str(x.relative_to(root).as_posix()) for x in _paths(root)}
    actual = {x["file"] for x in manifest["equity_files"]}
    if expected != actual or len(actual) != len(manifest["equity_files"]):
        raise ValueError("Cold archive file inventory does not match annual replay")
    restored = 0
    for row in manifest["equity_files"]:
        relative = Path(row["file"])
        path = _safe(root / relative, root)
        archive = _safe(path.with_name(EQUITY_FILE + ".gz"), root)
        archived_hash, archived_size = _digest(archive)
        if (archived_hash != row["archive_sha256"]
                or archived_size != row["archive_bytes"]):
            raise ValueError("Frozen compressed byte hash mismatch")
        _verify_archive(archive, row["sha256"], row["original_bytes"])
        if path.exists():
            if _digest(path) != (row["sha256"], row["original_bytes"]):
                raise ValueError("Existing raw equity evidence differs")
            continue
        fd, temp = tempfile.mkstemp(prefix=".nrfx_restore_", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as out, gzip.open(archive, "rb") as zipped:
                shutil.copyfileobj(zipped, out, length=1024*1024)
                out.flush()
                os.fsync(out.fileno())
            if _digest(Path(temp)) != (row["sha256"], row["original_bytes"]):
                raise ValueError("Restored equity evidence SHA mismatch")
            try:
                os.link(temp, path)
                restored += 1
            except FileExistsError:
                if _digest(path) != (row["sha256"], row["original_bytes"]):
                    raise ValueError("Concurrent equity restoration differs")
        finally:
            Path(temp).unlink(missing_ok=True)
    return {"restored_files": restored, "verified_files": len(expected),
            "independent_oos_proven": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", required=True, type=Path)
    parser.add_argument("--mode", choices=("archive", "restore"), required=True)
    parser.add_argument("--prune-raw", action="store_true")
    args = parser.parse_args(argv)
    if args.prune_raw and args.mode != "archive":
        raise ValueError("Prune applies only when archiving")
    result = (freeze_equity_storage(args.generation, prune_raw=args.prune_raw)
              if args.mode == "archive" else
              restore_equity_storage(args.generation))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
