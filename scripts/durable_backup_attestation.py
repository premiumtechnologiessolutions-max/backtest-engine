"""Consistent SQLite WAL backup and fail-closed offline restore.

ENGINE CONSTRUCTION ONLY: never executes a strategy, changes job state,
requeues a worker or grants result acceptance. Restore requires a *new*
target path and leaves all leases and attempt history untouched for review.

The manifest is a corruption detector, NOT a cryptographic signature: someone
who can edit both backup and manifest may forge both. Protect snapshot roots
with OS permissions and add externally anchored signatures before production.
"""
from __future__ import annotations

from contextlib import closing

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
import urllib.parse

from scripts.durable_operations_gate import evaluate

SCHEMA = "NRFX_SQLITE_BACKUP_ATTESTATION_V1"
_NAME = re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_MANIFEST_BYTES = 32768
_MAX_SNAPSHOT_BYTES = 2 * 1024**3


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_file(path: Path) -> tuple[str, int]:
    size = 0
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            chunk = source.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > _MAX_SNAPSHOT_BYTES:
                raise ValueError("Control-plane snapshot exceeds safety bound")
            digest.update(chunk)
    return digest.hexdigest(), size


def _safe_file(path: Path) -> None:
    if (path.is_symlink() or path.parent.is_symlink()
            or not path.is_file()):
        raise ValueError("Unsafe or missing SQLite file")


def _safe_directory(path: Path) -> None:
    if path.is_symlink() or path.parent.is_symlink() or not path.is_dir():
        raise ValueError("Backup directory must exist and not be symlinked")


def _clock(now_ms: int | None) -> int:
    value = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    if type(value) is not int or value < 0:
        raise ValueError("Invalid backup capture clock")
    return value


def _write_durable(path: Path, data: bytes) -> None:
    with path.open("xb") as output:
        if os.name == "posix":
            os.fchmod(output.fileno(), 0o600)
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def _sync_dir(path: Path) -> None:
    if os.name != "posix":
        return
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _frozen_manifest(state: Path, now: int, *, stage: Path) -> dict:
    code, report = evaluate(stage, now_ms=now)
    if code not in (0, 2):
        raise ValueError("SQLite backup does not pass durable integrity gate")
    digest, byte_count = _sha_file(stage)
    body = {
        "schema": SCHEMA, "status": "VERIFIED_CONTROL_STATE_ONLY",
        "captured_at_ms": now,
        "snapshot_file": "state.sqlite3",
        "snapshot_sha256": digest, "snapshot_bytes": byte_count,
        "health_gate_code": code,
        "health_gate_report_sha256": _digest(report),
        "jobs_observed": report["operations"]["total_jobs"],
        "attempts_observed": report["operations"]["total_attempts"],
        "resume_automatically_authorized": False,
        "market_data_included": False,
        "research_results_accepted": False,
    }
    return {**body, "manifest_sha256": _digest(body)}


def backup_durable_state(database: Path, backup_root: Path, snapshot_id: str,
                         *, now_ms: int | None = None) -> dict:
    """Create an immutable-directory consistent snapshot using SQLite backup API.

    SQLite's connection.backup() includes committed WAL changes even while
    other connections use WAL. A partially written directory is never
    published. Same snapshot ID is never replaced.
    """
    database, root = Path(database), Path(backup_root)
    _safe_file(database)
    _safe_directory(root)
    if type(snapshot_id) is not str or not _NAME.fullmatch(snapshot_id):
        raise ValueError("Invalid bounded snapshot ID")
    now = _clock(now_ms)
    target = root / snapshot_id
    if target.exists() or target.is_symlink():
        raise ValueError("Immutable backup snapshot ID already exists")
    temp = Path(tempfile.mkdtemp(prefix=".nrfx-backup-staging-", dir=root))
    try:
        copy = temp / "state.sqlite3"
        uri = "file:" + urllib.parse.quote(str(database.resolve())) + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=30)) as origin:
            origin.execute("PRAGMA query_only=ON")
            with closing(sqlite3.connect(str(copy), timeout=30)) as destination:
                origin.backup(destination, pages=256, sleep=0.05)
                destination.commit()
        # Close all SQLite handles before checksum and complete integrity audit.
        with copy.open("rb") as stream:
            os.fsync(stream.fileno())
        manifest = _frozen_manifest(database, now, stage=copy)
        _write_durable(temp / "manifest.json", _canonical(manifest) + b"\n")
        _sync_dir(temp)
        if target.exists() or target.is_symlink():
            raise ValueError("Concurrent immutable backup publication conflict")
        os.rename(temp, target)
        _sync_dir(root)
        return {
            "schema": SCHEMA, "snapshot_id": snapshot_id,
            "snapshot_sha256": manifest["snapshot_sha256"],
            "manifest_sha256": manifest["manifest_sha256"],
            "health_gate_code": manifest["health_gate_code"],
            "jobs_observed": manifest["jobs_observed"],
            "attempts_observed": manifest["attempts_observed"],
            "status": "BACKUP_PUBLISHED_REVIEW_ONLY",
            "worker_started": False, "research_executed": False,
            "automatic_resume": False,
        }
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def _json_exact(path: Path) -> dict:
    _safe_file(path)
    if path.stat().st_size > _MAX_MANIFEST_BYTES:
        raise ValueError("Oversized backup manifest")
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate backup manifest field")
            value[key] = item
        return value
    def bad_constant(value):
        raise ValueError("Nonfinite backup manifest field")
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"),
                            object_pairs_hook=unique, parse_constant=bad_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid backup manifest JSON") from exc
    if type(parsed) is not dict:
        raise ValueError("Backup manifest must be an object")
    return parsed


def verify_durable_backup(snapshot_dir: Path) -> dict:
    """Cross-check bytes, manifest and read-only integrity at capture time."""
    directory = Path(snapshot_dir)
    _safe_directory(directory)
    file = directory / "state.sqlite3"
    _safe_file(file)
    manifest = _json_exact(directory / "manifest.json")
    expected = {
        "schema", "status", "captured_at_ms", "snapshot_file",
        "snapshot_sha256", "snapshot_bytes", "health_gate_code",
        "health_gate_report_sha256", "jobs_observed", "attempts_observed",
        "resume_automatically_authorized", "market_data_included",
        "research_results_accepted", "manifest_sha256",
    }
    if set(manifest) != expected or manifest["schema"] != SCHEMA:
        raise ValueError("Unexpected frozen backup manifest schema")
    if (manifest["status"] != "VERIFIED_CONTROL_STATE_ONLY"
            or manifest["snapshot_file"] != "state.sqlite3"
            or any(manifest[k] is not False for k in (
                "resume_automatically_authorized", "market_data_included",
                "research_results_accepted"))
            or type(manifest["captured_at_ms"]) is not int
            or manifest["captured_at_ms"] < 0
            or type(manifest["snapshot_bytes"]) is not int
            or manifest["snapshot_bytes"] <= 0
            or type(manifest["health_gate_code"]) is not int
            or manifest["health_gate_code"] not in (0, 2)
            or any(type(manifest[k]) is not int or manifest[k] < 0 for k in (
                "jobs_observed", "attempts_observed"))):
        raise ValueError("Unsafe or malformed frozen backup manifest")
    for field in ("snapshot_sha256", "health_gate_report_sha256", "manifest_sha256"):
        if type(manifest[field]) is not str or not _SHA.fullmatch(manifest[field]):
            raise ValueError("Invalid frozen backup digest")
    if _digest({k: v for k, v in manifest.items()
                if k != "manifest_sha256"}) != manifest["manifest_sha256"]:
        raise ValueError("Backup manifest fingerprint mismatch")
    digest, byte_count = _sha_file(file)
    if digest != manifest["snapshot_sha256"] or byte_count != manifest["snapshot_bytes"]:
        raise ValueError("Backup SQLite bytes diverge from frozen manifest")
    code, report = evaluate(file, now_ms=manifest["captured_at_ms"])
    if (code != manifest["health_gate_code"]
            or code == 3
            or _digest(report) != manifest["health_gate_report_sha256"]
            or report["operations"]["total_jobs"] != manifest["jobs_observed"]
            or report["operations"]["total_attempts"] != manifest["attempts_observed"]):
        raise ValueError("Restored SQLite control-plane audit differs from backup")
    return {
        "schema": SCHEMA, "status": "VERIFIED_BACKUP_REVIEW_ONLY",
        "snapshot_sha256": digest, "manifest_sha256": manifest["manifest_sha256"],
        "jobs_observed": manifest["jobs_observed"],
        "attempts_observed": manifest["attempts_observed"],
        "health_gate_code": code,
        "resume_automatically_authorized": False,
        "research_results_accepted": False,
    }


def restore_durable_backup(snapshot_dir: Path, destination: Path) -> dict:
    """Restore copy to a NEW database path; never overwrite active control plane.

    Restore never changes job state. Any preserved RUNNING/RECONCILING attempts
    need separate independent OS-exit proof before future operation.
    """
    verified = verify_durable_backup(snapshot_dir)
    target = Path(destination)
    if (target.suffix.lower() != ".sqlite3"
            or target.is_symlink() or target.exists()
            or target.parent.is_symlink() or not target.parent.is_dir()):
        raise ValueError("Restore requires a new non-symlink SQLite destination")
    source = Path(snapshot_dir) / "state.sqlite3"
    fd, name = tempfile.mkstemp(prefix=".nrfx-restore-", suffix=".tmp",
                                dir=target.parent)
    temp = Path(name)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as inp:
            if os.name == "posix":
                os.fchmod(output.fileno(), 0o600)
            shutil.copyfileobj(inp, output, length=1 << 20)
            output.flush()
            os.fsync(output.fileno())
        sha, _ = _sha_file(temp)
        if sha != verified["snapshot_sha256"]:
            raise ValueError("Restored bytes differ from audited snapshot")
        # Hard-link to the private copied inode: atomic NO-REPLACE publish.
        # Never hard-link source snapshot into a mutable recovered database.
        os.link(temp, target)
        _sync_dir(target.parent)
        gate = evaluate(target)
        if gate[0] == 3:
            target.unlink()
            raise ValueError("Restored control plane failed latest gate")
        return {
            **verified,
            "status": "RESTORED_PENDING_OPERATOR_AND_SUPERVISOR_REVIEW",
            "restored_file_sha256": sha,
            "prior_attempts_and_leases_retained": True,
            "automatic_resume": False, "worker_started": False,
        }
    finally:
        temp.unlink(missing_ok=True)
