"""Fail-closed, local-only intake for frozen No Risk FX research requests.

This module NEVER executes jobs, reads market quotes, starts subprocesses,
contacts brokers, or asserts that a prospective evaluation has occurred.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# Preserve direct execution from a source checkout without installation.
try:
    from norisk_quant import frozen_queue
except ModuleNotFoundError as exc:
    if exc.name != "norisk_quant":
        raise
    sys.path.insert(0, str(ROOT / "src"))
    from norisk_quant import frozen_queue

FAMILY, COMMIT, SAFE_SPEC, DATE = (
    frozen_queue.FAMILY, frozen_queue.COMMIT, frozen_queue.SAFE_SPEC, frozen_queue.DATE,
)
_canonical, _sha, _period = frozen_queue._canonical, frozen_queue._sha, frozen_queue._period
_queue_directory, _verify = frozen_queue._queue_directory, frozen_queue._verify
_read_job_bytes, list_jobs = frozen_queue._read_job_bytes, frozen_queue.list_jobs
MAX_SOURCE_BYTES = 1_000_000


def _checked_repository_path(root: Path, relative: str) -> Path:
    """Reject symlinked path components, not only the final input file.

    This is a local provenance preflight, not a race-free filesystem sandbox.
    """
    if root.is_symlink():
        raise ValueError("Frozen input root must not be symlinked")
    candidate = root
    for part in PurePosixPath(relative).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ValueError("Frozen input path contains a symlinked ancestor")
    return candidate


def _read_source(root: Path, relative: str) -> str:
    if not SAFE_SPEC.fullmatch(relative) or ".." in PurePosixPath(relative).parts:
        raise ValueError("Frozen spec must be a safe docs/ or research/ markdown/JSON path")
    candidate = _checked_repository_path(root, relative)
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("Frozen spec missing, symlinked, or outside repository")
    if candidate.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Frozen spec exceeds size limit")
    return _sha(candidate.read_bytes())


def _registry_hash(root: Path) -> str:
    registry = _checked_repository_path(root, "research/strategy_factory_registry.json")
    if not registry.is_file() or not registry.resolve().is_relative_to(root.resolve()):
        raise ValueError("Registry unavailable or unsafe")
    if registry.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Registry exceeds size limit")
    data = registry.read_bytes()
    if not isinstance(json.loads(data), dict):
        raise ValueError("Registry must be a JSON object")
    return _sha(data)


def frozen_request(root: Path, family: str, spec: str, source_commit: str,
                   start: str, end: str) -> dict:
    """Fingerprint immutable input evidence; do not infer any backtest result."""
    if not isinstance(family, str) or not FAMILY.fullmatch(family):
        raise ValueError("Invalid FAC family identifier")
    if not isinstance(source_commit, str) or not COMMIT.fullmatch(source_commit):
        raise ValueError("Source commit must be a 40-character lowercase SHA")
    if _period(end) < _period(start):
        raise ValueError("Evaluation end precedes start")
    body = {
        "schema_version": 1,
        "mode": "OFFLINE_RESEARCH_ONLY",
        "family": family,
        "frozen_spec": spec,
        "frozen_spec_sha256": _read_source(root, spec),
        "registry_sha256": _registry_hash(root),
        "source_commit": source_commit,
        "evaluation_start": start,
        "evaluation_end": end,
        "status": "QUEUED_NOT_EXECUTED",
    }
    return {**body, "fingerprint": _sha(_canonical(body))}


def _fsync_queue_directory(directory: Path) -> None:
    """Persist directory entry publication where POSIX directory fsync exists."""
    if os.name == "posix":
        fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def enqueue(root: Path, request: dict) -> dict:
    """Write fully before publishing final name, without overwriting any job.

    A crash while writing can leave only an internal staging file. A consumer
    never observes a partial final *.json entry. Existing committed jobs are
    idempotent only when their bytes match the frozen request exactly.
    """
    record = _verify(request, request["fingerprint"] + ".json")
    directory = _queue_directory(root, create=True)
    target = directory / (record["fingerprint"] + ".json")
    payload = _canonical(record) + b"\n"

    def verify_existing() -> dict:
        try:
            existing = _read_job_bytes(target)
        except (ValueError, OSError) as exc:
            raise ValueError("Existing queue entry differs or is unsafe") from exc
        if existing != payload:
            raise ValueError("Existing queue entry differs from frozen request")
        return record

    if target.exists() or target.is_symlink():
        return verify_existing()
    fd, temporary = tempfile.mkstemp(prefix=".research-job-", suffix=".tmp",
                                     dir=directory)
    staging = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            if os.name == "nt":
                # Windows rename does not replace an existing destination.
                os.rename(staging, target)
            else:
                # Hard-link creates a final directory entry atomically and
                # fails with EEXIST; os.replace would overwrite another writer.
                os.link(staging, target, follow_symlinks=False)
        except FileExistsError:
            return verify_existing()
        _fsync_queue_directory(directory)
        return record
    finally:
        staging.unlink(missing_ok=True)
        _fsync_queue_directory(directory)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("enqueue", help="Record a frozen request; NEVER run it")
    add.add_argument("--family", required=True)
    add.add_argument("--spec", required=True)
    add.add_argument("--commit", required=True)
    add.add_argument("--start", required=True)
    add.add_argument("--end", required=True)
    sub.add_parser("list", help="Verify and list queued metadata only")
    args = parser.parse_args(argv)
    if args.command == "enqueue":
        result = enqueue(ROOT, frozen_request(ROOT, args.family, args.spec,
                                             args.commit, args.start, args.end))
    else:
        result = list_jobs(ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

