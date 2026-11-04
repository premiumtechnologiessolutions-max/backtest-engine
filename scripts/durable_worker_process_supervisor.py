"""Linux worker-identity / process-exit gate for future offline supervisor.

ENGINEERING CONSTRUCTION ONLY. Does not start, stop, kill, or resume a worker.
Never assume that lease expiry proves a process is gone. A group leader must
have a dedicated process group; group escape / daemonizing are not supported
by this future worker contract. Boot changes require operator recovery.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
import time

from scripts.durable_research_state import DurableResearchState

_SCHEMA = "NRFX_WORKER_PROCESS_LIFECYCLE_V1"
_BOOT_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                      r"[0-9a-f]{4}-[0-9a-f]{12}\Z")
_EXIT = "EXITED_SAME_BOOT_NO_GROUP_MEMBERS"
_ACTIVE = "ACTIVE"
_UNKNOWN_BOOT = "UNKNOWN_BOOT_CHANGED"
_UNKNOWN_PROC = "UNKNOWN_PROC_STATUS"


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    boot_id: str
    pid: int
    process_group: int
    start_ticks: int

    def __post_init__(self):
        if (type(self.boot_id) is not str or not _BOOT_ID.fullmatch(self.boot_id)
                or type(self.pid) is not int or self.pid < 2
                or type(self.process_group) is not int
                or self.process_group != self.pid
                or type(self.start_ticks) is not int
                or self.start_ticks <= 0):
            raise ValueError("Expected isolated Linux process-group leader identity")


class LinuxProcInspector:
    """Read-only /proc inspector; no worker creation or process signaling."""

    def __init__(self, proc_root: Path = Path("/proc")):
        if not sys.platform.startswith("linux") or os.name != "posix":
            raise RuntimeError("Linux-only process identity proof")
        self.root = Path(proc_root)

    def boot(self) -> str:
        boot = (self.root / "sys/kernel/random/boot_id").read_text().strip()
        if not _BOOT_ID.fullmatch(boot):
            raise ValueError("Untrusted Linux boot identifier")
        return boot

    @staticmethod
    def _stat(data: str) -> tuple[str, int, int]:
        # /proc/PID/stat field 2 (comm) may contain spaces and parentheses.
        # Parse after the LAST ')' so offsets are stable.
        right = data.rfind(")")
        left = data.find("(")
        if left < 0 or right < left:
            raise ValueError("Malformed Linux proc stat")
        rest = data[right + 1:].split()
        # After comm: state #3 index0; pgrp #5 index2;
        # starttime #22 index19.
        if len(rest) < 20:
            raise ValueError("Incomplete Linux process stat")
        state = rest[0]
        if state not in "RSDZTtXxKWPIN":
            raise ValueError("Unknown Linux process state")
        group, start = int(rest[2]), int(rest[19])
        if group < 1 or start <= 0:
            raise ValueError("Invalid Linux proc identity fields")
        return state, group, start

    def capture(self, pid: int) -> ProcessIdentity:
        if type(pid) is not int or pid < 2:
            raise ValueError("Invalid Linux process ID")
        state, group, ticks = self._stat(
            (self.root / str(pid) / "stat").read_text())
        if state in {"Z", "X", "x"} or group != pid:
            raise ValueError("Worker must be a live isolated process-group leader")
        return ProcessIdentity(self.boot(), pid, group, ticks)

    def observe_exit(self, identity: ProcessIdentity) -> str:
        """Observe the exact Linux process identity and its dedicated group.

        /proc enumeration is not a reliable exit proof when unrelated
        processes are unreadable or churn rapidly. A same-boot direct PID
        check establishes whether the recorded leader is still the *same*
        living process. A kernel process-group existence probe (signal 0,
        never a kill) then checks for surviving group members even when the
        leader already exited. EPERM and unknown OS errors fail closed.
        """
        if not isinstance(identity, ProcessIdentity):
            raise ValueError("Unknown process identity type")
        try:
            if self.boot() != identity.boot_id:
                return _UNKNOWN_BOOT
            try:
                state, group, ticks = self._stat(
                    (self.root / str(identity.pid) / "stat").read_text())
            except FileNotFoundError:
                state = group = ticks = None
            except (OSError, UnicodeError, ValueError):
                return _UNKNOWN_PROC
            if ticks == identity.start_ticks:
                if group != identity.process_group:
                    # Escape from isolated group may leave live work behind.
                    return _UNKNOWN_PROC
                if state not in {"Z", "X", "x"}:
                    return _ACTIVE
            # The original leader has exited/reaped, become zombie, or its
            # PID was reused. The group may STILL contain live descendants.
            # os.killpg(group, 0) asks the kernel whether it exists; signal
            # zero does NOT terminate or modify the group's processes.
            try:
                os.killpg(identity.process_group, 0)
            except ProcessLookupError:
                return _EXIT
            except PermissionError:
                return _ACTIVE  # Could be alive under a different UID.
            except OSError:
                return _UNKNOWN_PROC
            return _ACTIVE
        except (OSError, UnicodeError, ValueError):
            return _UNKNOWN_PROC

def _clock(value: int | None) -> int:
    now = time.time_ns() // 1_000_000 if value is None else value
    if type(now) is not int or now < 0:
        raise ValueError("Invalid monotonic control-plane wall clock")
    return now


def _table(db) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS supervisor_process_identity("
        "attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id), "
        "request_id TEXT NOT NULL REFERENCES jobs(request_id), "
        "fencing_token INTEGER NOT NULL, worker TEXT NOT NULL, "
        "boot_id TEXT NOT NULL, pid INTEGER NOT NULL, "
        "process_group INTEGER NOT NULL, start_ticks INTEGER NOT NULL, "
        "bound_ms INTEGER NOT NULL)"
    )


def attach_process_identity(store: DurableResearchState, claim: dict,
                            pid: int, inspector: LinuxProcInspector, *,
                            now_ms: int | None = None) -> dict:
    """Freeze a real isolated process identity against the current lease.

    The inspector may be replaced only in synthetic unit tests. Attaching
    process metadata never authorizes or launches its work.
    """
    if not isinstance(store, DurableResearchState) or type(claim) is not dict:
        raise ValueError("Missing trusted durable attempt")
    now = _clock(now_ms)
    identity = inspector.capture(pid)
    if inspector.observe_exit(identity) != _ACTIVE:
        raise ValueError("Worker process is not provably active")
    with store._write() as db:
        row = store._owned(
            db, claim["request_id"], claim["attempt_id"],
            claim["fencing_token"], claim["worker"], now)
        if (row["state"] != "RUNNING"
                or row["attempt_no"] != claim["attempt_no"]
                or inspector.observe_exit(identity) != _ACTIVE):
            raise ValueError("Cannot attach stopped or non-running worker")
        _table(db)
        fields = (
            claim["attempt_id"], claim["request_id"], claim["fencing_token"],
            claim["worker"], identity.boot_id, identity.pid,
            identity.process_group, identity.start_ticks,
        )
        prev = db.execute(
            "SELECT attempt_id, request_id, fencing_token, worker, boot_id,"
            " pid, process_group, start_ticks FROM supervisor_process_identity"
            " WHERE attempt_id=?", (claim["attempt_id"],)
        ).fetchone()
        if prev is None:
            db.execute(
                "INSERT INTO supervisor_process_identity("
                "attempt_id, request_id, fencing_token, worker, boot_id,"
                " pid, process_group, start_ticks, bound_ms)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*fields, now))
        elif tuple(prev) != fields:
            raise ValueError("Immutable worker process identity drift")
    return {
        "schema": _SCHEMA, "request_id": claim["request_id"],
        "attempt_id": claim["attempt_id"],
        "pid": identity.pid, "start_ticks": identity.start_ticks,
        "lease_authority_granted_by_attachment": False,
        "research_executed": False,
    }


def recover_expired_process_after_exit(
    store: DurableResearchState, request_id: str,
    inspector: LinuxProcInspector, *, now_ms: int | None = None,
) -> bool:
    """Requeue ONLY when same-boot OS process group absence is verified.

    Atomic compare-and-update is performed while holding the SQLite write
    lock; no boolean caller assertion substitutes for process proof.
    Does not kill or spawn. If no identity was attached, fail closed.
    """
    now = _clock(now_ms)
    with store._write() as db:
        job = db.execute(
            "SELECT * FROM jobs WHERE request_id=?", (request_id,)
        ).fetchone()
        if (job is None or job["state"] not in ("RUNNING", "RECONCILING")
                or job["lease_until_ms"] is None or job["lease_until_ms"] > now
                or job["attempt_id"] is None):
            raise ValueError("No expired owned attempt eligible for recovery")
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table'"
            " AND name='supervisor_process_identity'"
        ).fetchone()
        if exists is None:
            raise ValueError("No authenticated OS worker identity")
        record = db.execute(
            "SELECT * FROM supervisor_process_identity WHERE attempt_id=?",
            (job["attempt_id"],)
        ).fetchone()
        if (record is None or record["request_id"] != request_id
                or record["fencing_token"] != job["fencing_token"]
                or record["worker"] != job["worker"]):
            raise ValueError("Stale or disconnected OS worker identity")
        identity = ProcessIdentity(
            record["boot_id"], record["pid"],
            record["process_group"], record["start_ticks"])
        if inspector.observe_exit(identity) != _EXIT:
            raise ValueError("Operating system has not proven worker exit")
        old = job["state"]
        db.execute(
            "UPDATE jobs SET state='QUEUED', version=version+1,"
            " worker=NULL, attempt_id=NULL, lease_until_ms=NULL,"
            " updated_ms=? WHERE request_id=? AND attempt_id=?"
            " AND fencing_token=?",
            (now, request_id, job["attempt_id"], job["fencing_token"]))
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            raise ValueError("Concurrent durable worker identity drift")
        store._event(db, request_id, old, "QUEUED", job["fencing_token"], now)
    return True
