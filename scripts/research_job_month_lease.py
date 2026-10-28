"""POSIX-only, local-exclusive month-slot reservation for frozen research jobs.

A reservation is NOT a backtest, checkpoint, data verification, or completion.
No subprocess, broker, network, or private market-data access is performed.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import fcntl
import os
from pathlib import Path
import re
import stat
from typing import Iterator

try:
    from scripts.research_job_plan_snapshot import verify_plan
except ModuleNotFoundError:  # direct script invocation from repository root
    from research_job_plan_snapshot import verify_plan

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MONTH = re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])\Z")


def _lock_directory(root: Path) -> Path:
    reports = root / "reports"
    if reports.is_symlink():
        raise ValueError("Symlinked reports directory")
    directory = reports / "research_job_locks"
    if directory.is_symlink():
        raise ValueError("Symlinked research lock directory")
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    info = directory.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("Research lock path is not a directory")
    if os.name == "posix" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
        raise ValueError("Research lock directory must be owner-only")
    return directory


def _closed_slot(plan: dict, fingerprint: str, month: str, now: datetime) -> dict:
    if (type(plan) is not dict or plan.get("request_fingerprint") != fingerprint
            or plan.get("status") != "PLANNED_ONLY_NOT_EXECUTED"
            or type(plan.get("backtests_executed")) is not int
            or plan["backtests_executed"] != 0
            or type(plan.get("source_verified_months")) is not int
            or plan["source_verified_months"] != 0):
        raise ValueError("Unverified or executed monthly plan")
    slots = plan.get("slots")
    if type(slots) is not list or not 1 <= len(slots) <= 120:
        raise ValueError("Invalid monthly plan slots")
    matches = [slot for slot in slots if type(slot) is dict and slot.get("month") == month]
    if len(matches) != 1:
        raise ValueError("Month not present exactly once in frozen plan")
    slot = matches[0]
    if (type(slot.get("slot_fingerprint")) is not str
            or not HEX64.fullmatch(slot["slot_fingerprint"])):
        raise ValueError("Invalid frozen month fingerprint")
    try:
        start = date.fromisoformat(slot["start_utc"])
        end = date.fromisoformat(slot["end_exclusive_utc"])
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("Invalid frozen month bounds") from exc
    if (start.strftime("%Y-%m") != month or start.day != 1
            or end != date(start.year + (start.month == 12),
                           1 if start.month == 12 else start.month + 1, 1)):
        raise ValueError("Frozen month is not an exact UTC calendar month")
    if now.date() < end:
        raise ValueError("Month has not closed in UTC")
    return slot


@contextmanager
def reserve_closed_month(root: Path, fingerprint: str, month: str,
                         *, now_utc: datetime | None = None) -> Iterator[dict]:
    """Hold one OS lock per frozen month, fail closed on competing reservations.

    Locks are automatically released on process death; files persist empty.
    A future worker must separately verify private source, enforce resource
    limits and checkpoint actual results. This function NEVER runs a worker.
    """
    if os.name != "posix":
        raise ValueError("Research month reservation requires POSIX flock")
    if type(fingerprint) is not str or not HEX64.fullmatch(fingerprint):
        raise ValueError("Invalid frozen request fingerprint")
    if type(month) is not str or not MONTH.fullmatch(month):
        raise ValueError("Invalid UTC month")
    now = datetime.now(timezone.utc) if now_utc is None else now_utc
    if (type(now) is not datetime or now.tzinfo is None
            or now.utcoffset() != timedelta(0)):
        raise ValueError("Reservation clock must be UTC-aware")
    # Snapshot verification includes frozen spec, registry and exact clean HEAD.
    initial = _closed_slot(verify_plan(root, fingerprint), fingerprint, month, now)
    directory = _lock_directory(root)
    path = directory / (fingerprint + "." + month + ".lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_size != 0 or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise ValueError("Unsafe or nonempty research month lock file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Month already reserved by another research process") from exc
        # Eliminate the gap between preflight and lock acquisition.
        checked = _closed_slot(verify_plan(root, fingerprint), fingerprint, month, now)
        if checked != initial:
            raise ValueError("Frozen monthly plan changed while acquiring reservation")
        yield {
            "request_fingerprint": fingerprint,
            "month": month,
            "slot_fingerprint": checked["slot_fingerprint"],
            "status": "RESERVED_ONLY_NO_BACKTEST",
            "backtests_executed": 0,
            "source_verified": False,
            "monthly_pnl_usd_per_oz": None,
            "observed_m1_floating_dd_usd_per_oz": None,
        }
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
