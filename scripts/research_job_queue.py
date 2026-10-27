"""Fail-closed, local-only intake for frozen No Risk FX research requests.

This module NEVER executes jobs, reads market quotes, starts subprocesses,
contacts brokers, or asserts that a prospective evaluation has occurred.
"""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

ROOT = Path(__file__).resolve().parents[1]
FAMILY = re.compile(r"NRF-FAC-[0-9]{3}[A-Z]?\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
SAFE_SPEC = re.compile(r"(?:docs|research)/[A-Za-z0-9._/-]+\.(?:md|json)\Z")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
MAX_SOURCE_BYTES = 1_000_000


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_source(root: Path, relative: str) -> str:
    if not SAFE_SPEC.fullmatch(relative) or ".." in PurePosixPath(relative).parts:
        raise ValueError("Frozen spec must be a safe docs/ or research/ markdown/JSON path")
    candidate = root / relative
    if candidate.is_symlink() or not candidate.is_file() or not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("Frozen spec missing, symlinked, or outside repository")
    if candidate.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Frozen spec exceeds size limit")
    return _sha(candidate.read_bytes())


def _registry_hash(root: Path) -> str:
    registry = root / "research" / "strategy_factory_registry.json"
    if registry.is_symlink() or not registry.is_file() or not registry.resolve().is_relative_to(root.resolve()):
        raise ValueError("Registry unavailable or unsafe")
    if registry.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Registry exceeds size limit")
    data = registry.read_bytes()
    if not isinstance(json.loads(data), dict):
        raise ValueError("Registry must be a JSON object")
    return _sha(data)


def _period(value: str) -> date:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        raise ValueError("Evaluation dates must use YYYY-MM-DD")
    return date.fromisoformat(value)


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


def _queue_directory(root: Path, create: bool) -> Path:
    reports = root / "reports"
    if reports.is_symlink():
        raise ValueError("Refusing symlinked reports directory")
    directory = reports / "research_jobs"
    if directory.is_symlink():
        raise ValueError("Refusing symlinked queue directory")
    if create:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not directory.exists():
        return directory
    if not directory.is_dir():
        raise ValueError("Queue location is not a directory")
    if os.name == "posix":
        stat = directory.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise ValueError("Queue directory must be owner-only (0700)")
    return directory


def _verify(record: dict, filename: str) -> dict:
    if not isinstance(record, dict) or set(record) != {
        "schema_version", "mode", "family", "frozen_spec", "frozen_spec_sha256",
        "registry_sha256", "source_commit", "evaluation_start", "evaluation_end",
        "status", "fingerprint",
    }:
        raise ValueError("Malformed research queue record")
    if (type(record["schema_version"]) is not int or record["schema_version"] != 1
            or record["mode"] != "OFFLINE_RESEARCH_ONLY"
            or record["status"] != "QUEUED_NOT_EXECUTED"):
        raise ValueError("Unsupported or misleading queue state")
    if type(record["family"]) is not str or not FAMILY.fullmatch(record["family"]):
        raise ValueError("Invalid queue family")
    spec = record["frozen_spec"]
    if (type(spec) is not str or not SAFE_SPEC.fullmatch(spec)
            or ".." in PurePosixPath(spec).parts):
        raise ValueError("Invalid queue frozen spec")
    if type(record["source_commit"]) is not str or not COMMIT.fullmatch(record["source_commit"]):
        raise ValueError("Invalid queue source commit")
    for field in ("frozen_spec_sha256", "registry_sha256"):
        if type(record[field]) is not str or not re.fullmatch(r"[0-9a-f]{64}", record[field]):
            raise ValueError(f"Invalid queue {field}")
    if _period(record["evaluation_end"]) < _period(record["evaluation_start"]):
        raise ValueError("Invalid queue evaluation period")
    fingerprint = record["fingerprint"]
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("Invalid fingerprint")
    if _sha(_canonical({k: v for k, v in record.items() if k != "fingerprint"})) != fingerprint:
        raise ValueError("Tampered research queue record")
    if filename != fingerprint + ".json":
        raise ValueError("Queue filename does not match fingerprint")
    return record


def _read_job_bytes(path: Path) -> bytes:
    """Reject links, unsafe permissions and oversized entries before parsing."""
    if path.is_symlink():
        raise ValueError("Symlinked queue record")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Queue record must be a regular, unlinked file")
        if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError("Queue record must be owner-only (0600)")
        if info.st_size > 8192:
            raise ValueError("Oversized queue record")
        return stream.read(8193)


def enqueue(root: Path, request: dict) -> dict:
    """Atomic, idempotent, owner-only intake; deliberately no worker."""
    record = _verify(request, request["fingerprint"] + ".json")
    directory = _queue_directory(root, create=True)
    target = directory / (record["fingerprint"] + ".json")
    payload = _canonical(record) + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags, 0o600)
    except FileExistsError:
        try:
            existing = _read_job_bytes(target)
        except (ValueError, OSError) as exc:
            raise ValueError("Existing queue entry differs or is unsafe") from exc
        if existing != payload:
            raise ValueError("Existing queue entry differs from frozen request")
        return record
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return record


def list_jobs(root: Path) -> list[dict]:
    directory = _queue_directory(root, create=False)
    if not directory.exists():
        return []
    jobs = []
    for file in sorted(directory.iterdir()):
        if file.suffix != ".json":
            raise ValueError("Unexpected queue entry")
        jobs.append(_verify(json.loads(_read_job_bytes(file)), file.name))
    return jobs


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
