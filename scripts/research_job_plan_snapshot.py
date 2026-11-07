"""Owner-only immutable monthly *plan* snapshots; never execution checkpoints.

Snapshots bind frozen, preflight-verified requests to deterministic UTC slots.
No market quotes, workers, returns, broker access or OOS certification.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat

try:
    from scripts.research_job_month_plan import plan_job
    from scripts.research_job_queue import ROOT, _canonical, _queue_directory, _sha
except ModuleNotFoundError:
    from research_job_month_plan import plan_job
    from research_job_queue import ROOT, _canonical, _queue_directory, _sha

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES = 32768


def _directory(root: Path, *, create: bool) -> Path:
    parent = _queue_directory(root, create=create)
    directory = parent / "monthly_plans"
    if directory.is_symlink():
        raise ValueError("Symlinked monthly-plan directory")
    if create:
        directory.mkdir(mode=0o700, exist_ok=True)
    if not directory.exists():
        raise ValueError("No persisted monthly plans")
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("Invalid monthly-plan directory")
    if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError("Monthly-plan directory must be owner-only")
    return directory


def _expected(root: Path, fingerprint: str) -> bytes:
    if type(fingerprint) is not str or not HEX64.fullmatch(fingerprint):
        raise ValueError("Invalid request fingerprint")
    # Rechecks queue integrity, frozen hashes, exact clean checkout and HEAD.
    planned = plan_job(root, fingerprint)
    if planned["request_fingerprint"] != fingerprint or not planned["planning_only"]:
        raise ValueError("Invalid monthly-plan provenance")
    slots = []
    for slot in planned["slots"]:
        ident = slot["slot_fingerprint"]
        if type(ident) is not str or not HEX64.fullmatch(ident):
            raise ValueError("Invalid deterministic month-slot fingerprint")
        slots.append({
            "month": slot["month"],
            "start_utc": slot["month_start_utc"],
            "end_exclusive_utc": slot["month_end_exclusive_utc"],
            "slot_fingerprint": ident,
        })
    if not slots or len(slots) > 120:
        raise ValueError("Invalid month-slot count")
    body = {
        "schema_version": 1,
        "request_fingerprint": fingerprint,
        "status": "PLANNED_ONLY_NOT_EXECUTED",
        "source_verified_months": 0,
        "backtests_executed": 0,
        "slots": slots,
    }
    record = {**body, "snapshot_sha256": _sha(_canonical(body))}
    payload = _canonical(record) + b"\n"
    if len(payload) > MAX_BYTES:
        raise ValueError("Monthly-plan snapshot too large")
    return payload


def _read(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError("Symlinked monthly-plan snapshot")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Unsafe monthly-plan file type or hardlink")
        if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError("Monthly-plan snapshot must be owner-only")
        if info.st_size > MAX_BYTES:
            raise ValueError("Oversized monthly-plan snapshot")
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Oversized monthly-plan snapshot")
    return data


def persist_plan(root: Path, fingerprint: str) -> dict:
    """Idempotent O_EXCL snapshot. Never overwrite a changed/corrupt record."""
    payload = _expected(root, fingerprint)  # preflight BEFORE any write
    directory = _directory(root, create=True)
    target = directory / (fingerprint + ".json")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags, 0o600)
    except FileExistsError:
        if _read(target) != payload:
            raise ValueError("Existing monthly-plan snapshot differs or is unsafe")
        return json.loads(payload)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return json.loads(payload)


def verify_plan(root: Path, fingerprint: str) -> dict:
    """Recompute every slot from verified frozen inputs; reject any drift."""
    payload = _expected(root, fingerprint)
    path = _directory(root, create=False) / (fingerprint + ".json")
    if _read(path) != payload:
        raise ValueError("Persisted monthly-plan snapshot changed or is stale")
    return json.loads(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("persist", "verify"))
    parser.add_argument("--fingerprint", required=True)
    args = parser.parse_args(argv)
    result = (persist_plan if args.action == "persist" else verify_plan)(ROOT, args.fingerprint)
    print(json.dumps({
        "request_fingerprint": result["request_fingerprint"],
        "snapshot_sha256": result["snapshot_sha256"],
        "slots": len(result["slots"]),
        "status": result["status"],
        "backtests_executed": 0,
        "source_verified_months": 0,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
