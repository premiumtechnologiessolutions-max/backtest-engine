"""Frozen historical request identity and the existing owner-only file queue reader."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

FAMILY = re.compile(r"NRF-FAC-[0-9]{3}[A-Z]?\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
SAFE_SPEC = re.compile(r"(?:docs|research)/[A-Za-z0-9._/-]+\.(?:md|json)\Z")
DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _period(value: str) -> date:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        raise ValueError("Evaluation dates must use YYYY-MM-DD")
    return date.fromisoformat(value)


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
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Queue record must be a regular, unlinked file")
        if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError("Queue record must be owner-only (0600)")
        if info.st_size > 8192:
            raise ValueError("Oversized queue record")
        return stream.read(8193)


def list_jobs(root: Path, *, limit: int | None = None) -> list[dict]:
    directory = _queue_directory(root, create=False)
    if not directory.exists():
        return []
    jobs = []
    for file in sorted(directory.iterdir()):
        # The immutable planner stores snapshots in a dedicated owner-only
        # subdirectory. Do not treat it as a queued job, and never follow
        # a symlink or silently ignore any other unexpected queue entry.
        if file.name == "monthly_plans":
            if file.is_symlink() or not file.is_dir():
                raise ValueError("Unsafe monthly-plan queue subdirectory")
            info = file.stat()
            if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
                raise ValueError("Monthly-plan queue subdirectory must be owner-only")
            continue
        # Staging is never a committed queue record. An abrupt exit can
        # strand one; it is intentionally excluded from the reader and a
        # subsequent enqueue can safely retry without reusing staged bytes.
        if file.name.startswith(".research-job-") and file.name.endswith(".tmp"):
            if file.is_symlink() or not file.is_file():
                raise ValueError("Unsafe queue staging entry")
            continue
        if file.suffix != ".json":
            raise ValueError("Unexpected queue entry")
        # A checksum of parsed JSON is insufficient: duplicate keys and
        # alternate encodings can represent the same object while altering
        # an immutable queue record. Refuse every noncanonical disk byte.
        raw = _read_job_bytes(file)
        record = _verify(json.loads(raw), file.name)
        if raw != _canonical(record) + b"\n":
            raise ValueError("Noncanonical immutable queue record bytes")
        jobs.append(record)
        if limit is not None and len(jobs) > limit:
            raise ValueError(f"Import exceeds {limit} historical requests")
    return jobs
