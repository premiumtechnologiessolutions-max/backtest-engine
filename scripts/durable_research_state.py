"""Durable, fail-closed admission and leasing for the existing frozen research queue.

This is a single-host SQLite *control-plane pilot*. It imports only immutable
requests validated by scripts.research_job_queue. No worker is launched, no
backtest is certified and there is deliberately NO ACCEPTED transition until an
independent source/accounting/receipt validator is wired in.

SQLite transactions and monotonically increasing fencing tokens prevent
concurrent or expired workers from claiming authority over a request.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

from scripts.research_job_queue import _verify, list_jobs

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_WORKER = re.compile(r"[A-Za-z0-9_.:-]{1,80}\Z")
_TERMINAL = frozenset({"CANCELLED", "QUARANTINED"})
_SCHEMA = "NRFX_DURABLE_INTAKE_V1"


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _canonical(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class DurableResearchState:
    """One SQLite file, exclusive metadata transactions; no broker privileges."""

    def __init__(self, database: Path):
        self.database = Path(database)
        if self.database.is_symlink() or self.database.exists() and not self.database.is_file():
            raise ValueError("Unsafe durable research database")
        if self.database.parent.is_symlink():
            raise ValueError("Unsafe durable research parent directory")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE IF NOT EXISTS jobs ("
                       "request_id TEXT PRIMARY KEY, frozen_json TEXT NOT NULL, "
                       "state TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0, "
                       "fencing_token INTEGER NOT NULL DEFAULT 0, "
                       "attempt_no INTEGER NOT NULL DEFAULT 0, "
                       "attempt_id TEXT, worker TEXT, lease_until_ms INTEGER, "
                       "created_ms INTEGER NOT NULL, updated_ms INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS attempts ("
                       "attempt_id TEXT PRIMARY KEY, request_id TEXT NOT NULL "
                       "REFERENCES jobs(request_id), attempt_no INTEGER NOT NULL, "
                       "fencing_token INTEGER NOT NULL, worker TEXT NOT NULL, "
                       "claimed_ms INTEGER NOT NULL, "
                       "UNIQUE(request_id, attempt_no), "
                       "UNIQUE(request_id, fencing_token))")
            db.execute("CREATE TABLE IF NOT EXISTS events ("
                       "event_id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "request_id TEXT NOT NULL REFERENCES jobs(request_id), "
                       "from_state TEXT, to_state TEXT NOT NULL, "
                       "fencing_token INTEGER NOT NULL, created_ms INTEGER NOT NULL)")
            db.commit()

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(str(self.database), timeout=30, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=30000")
            yield db
        finally:
            db.close()

    @contextmanager
    def _write(self):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
            except BaseException:
                db.execute("ROLLBACK")
                raise
            else:
                db.execute("COMMIT")

    @staticmethod
    def _event(db, request_id, before, after, token, now):
        db.execute("INSERT INTO events("
                   "request_id, from_state, to_state, fencing_token, created_ms)"
                   " VALUES (?, ?, ?, ?, ?)",
                   (request_id, before, after, token, now))

    def ingest_record(self, record: dict) -> str:
        """Import an immutable request, never self-declared execution evidence."""
        if type(record) is not dict or type(record.get("fingerprint")) is not str:
            raise ValueError("Invalid frozen queue record")
        request_id = record["fingerprint"]
        _verify(record, request_id + ".json")
        frozen = _canonical(record)
        now = _now_ms()
        with self._write() as db:
            existing = db.execute("SELECT frozen_json FROM jobs WHERE request_id=?",
                                  (request_id,)).fetchone()
            if existing is not None:
                if existing["frozen_json"] != frozen:
                    raise ValueError("Immutable request content drift")
                return request_id
            db.execute("INSERT INTO jobs(request_id, frozen_json, state, "
                       "created_ms, updated_ms) VALUES (?, ?, 'QUEUED', ?, ?)",
                       (request_id, frozen, now, now))
            self._event(db, request_id, None, "QUEUED", 0, now)
        return request_id

    def import_existing_queue(self, root: Path) -> int:
        """Bridge the established frozen-file intake into durable metadata."""
        records = list_jobs(Path(root))  # Existing reader verifies file bytes.
        for record in records:
            self.ingest_record(record)
        return len(records)

    def claim_next(self, worker: str, *, lease_seconds: int = 120,
                   now_ms: int | None = None) -> dict | None:
        """Atomically assign one due request and strictly increment its fence."""
        if type(worker) is not str or not _WORKER.fullmatch(worker):
            raise ValueError("Invalid worker ID")
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid bounded lease duration")
        now = _now_ms() if now_ms is None else now_ms
        if type(now) is not int or now < 0:
            raise ValueError("Invalid UTC lease clock")
        with self._write() as db:
            row = db.execute(
                "SELECT * FROM jobs WHERE state='QUEUED' "
                "OR (state IN ('RUNNING', 'RECONCILING') "
                "AND lease_until_ms<=?) ORDER BY created_ms, request_id LIMIT 1",
                (now,),
            ).fetchone()
            if row is None:
                return None
            attempt_id = uuid.uuid4().hex
            token = row["fencing_token"] + 1
            attempt_no = row["attempt_no"] + 1
            expires = now + lease_seconds * 1000
            db.execute("UPDATE jobs SET state='RUNNING', version=version+1, "
                       "fencing_token=?, attempt_no=?, attempt_id=?, "
                       "worker=?, lease_until_ms=?, updated_ms=? "
                       "WHERE request_id=?",
                       (token, attempt_no, attempt_id, worker, expires, now,
                        row["request_id"]))
            db.execute("INSERT INTO attempts("
                       "attempt_id, request_id, attempt_no, fencing_token, "
                       "worker, claimed_ms) VALUES (?, ?, ?, ?, ?, ?)",
                       (attempt_id, row["request_id"], attempt_no, token, worker, now))
            self._event(db, row["request_id"], row["state"], "RUNNING", token, now)
            return {"request_id": row["request_id"], "attempt_id": attempt_id,
                    "attempt_no": attempt_no, "fencing_token": token, "worker": worker,
                    "lease_until_ms": expires, "frozen_request": json.loads(row["frozen_json"])}

    def heartbeat(self, request_id: str, attempt_id: str, fencing_token: int,
                  worker: str, *, lease_seconds: int = 120,
                  now_ms: int | None = None) -> int:
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease")
        now = _now_ms() if now_ms is None else now_ms
        if type(now) is not int or now < 0:
            raise ValueError("Invalid UTC lease clock")
        with self._write() as db:
            row = self._owned(db, request_id, attempt_id, fencing_token, worker, now)
            expires = now + lease_seconds * 1000
            db.execute("UPDATE jobs SET lease_until_ms=?, updated_ms=?, "
                       "version=version+1 WHERE request_id=?",
                       (expires, now, row["request_id"]))
            return expires

    @staticmethod
    def _owned(db, request_id, attempt_id, token, worker, now):
        row = db.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
        if (row is None or row["state"] not in {"RUNNING", "RECONCILING"}
                or type(token) is not int or row["fencing_token"] != token
                or row["attempt_id"] != attempt_id or row["worker"] != worker
                or row["lease_until_ms"] is None or row["lease_until_ms"] <= now):
            raise ValueError("Stale or unauthorized research attempt")
        return row

    def start_reconciliation(self, request_id: str, attempt_id: str,
                             fencing_token: int, worker: str,
                             *, now_ms: int | None = None) -> None:
        """Only records phase transition, NOT evidence acceptance."""
        now = _now_ms() if now_ms is None else now_ms
        with self._write() as db:
            row = self._owned(db, request_id, attempt_id, fencing_token, worker, now)
            if row["state"] != "RUNNING":
                raise ValueError("Attempt already reconciling")
            db.execute("UPDATE jobs SET state='RECONCILING', version=version+1, "
                       "updated_ms=? WHERE request_id=?", (now, request_id))
            self._event(db, request_id, "RUNNING", "RECONCILING", fencing_token, now)

    def quarantine(self, request_id: str, attempt_id: str, fencing_token: int,
                   worker: str, *, now_ms: int | None = None) -> None:
        """For invalid/incomplete research; never promotes results to accepted."""
        now = _now_ms() if now_ms is None else now_ms
        with self._write() as db:
            row = self._owned(db, request_id, attempt_id, fencing_token, worker, now)
            db.execute("UPDATE jobs SET state='QUARANTINED', version=version+1, "
                       "worker=NULL, lease_until_ms=NULL, updated_ms=? WHERE request_id=?",
                       (now, request_id))
            self._event(db, request_id, row["state"], "QUARANTINED", fencing_token, now)

    def cancel(self, request_id: str) -> str:
        """No partial result can become ACCEPTED through this pilot."""
        if type(request_id) is not str or not _HEX64.fullmatch(request_id):
            raise ValueError("Invalid request ID")
        now = _now_ms()
        with self._write() as db:
            row = db.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown research request")
            prior = row["state"]
            if prior in _TERMINAL or prior == "CANCEL_REQUESTED":
                return prior
            state = "CANCEL_REQUESTED" if prior in {"RUNNING", "RECONCILING"} else "CANCELLED"
            db.execute("UPDATE jobs SET state=?, version=version+1, "
                       "updated_ms=? WHERE request_id=?", (state, now, request_id))
            self._event(db, request_id, prior, state, row["fencing_token"], now)
            return state

    def acknowledge_cancel(self, request_id: str, attempt_id: str,
                           fencing_token: int, worker: str,
                           *, now_ms: int | None = None) -> None:
        """Cooperative worker cancellation, with attempt identity and fencing.

        A cancelled worker cannot use ordinary heartbeat/transition APIs.
        This is only a metadata acknowledgement; the supervisor must ensure
        the underlying process has actually stopped before acknowledging.
        """
        now = _now_ms() if now_ms is None else now_ms
        if type(now) is not int or now < 0:
            raise ValueError("Invalid UTC lease clock")
        with self._write() as db:
            row = db.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
            if (row is None or row["state"] != "CANCEL_REQUESTED"
                    or type(fencing_token) is not int
                    or row["fencing_token"] != fencing_token
                    or row["attempt_id"] != attempt_id or row["worker"] != worker
                    or row["lease_until_ms"] is None
                    or row["lease_until_ms"] <= now):
                raise ValueError("Stale or unauthorized cancellation acknowledgement")
            db.execute("UPDATE jobs SET state='CANCELLED', version=version+1, "
                       "worker=NULL, lease_until_ms=NULL, updated_ms=? "
                       "WHERE request_id=?", (now, request_id))
            self._event(db, request_id, "CANCEL_REQUESTED", "CANCELLED",
                        fencing_token, now)

    def finalize_expired_cancel(self, request_id: str, *, process_exit_confirmed: bool = False,
                                now_ms: int | None = None) -> bool:
        """Retire an expired cancellation after supervisor confirms process exit.

        Callers MUST first establish that the former worker process is dead;
        lease expiry alone does not terminate a process. This method is not a
        process killer and cannot publish research results.
        """
        if process_exit_confirmed is not True:
            raise ValueError("Supervisor must confirm worker process exit")
        now = _now_ms() if now_ms is None else now_ms
        if type(now) is not int or now < 0:
            raise ValueError("Invalid UTC lease clock")
        with self._write() as db:
            row = db.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown research request")
            if row["state"] == "CANCELLED":
                return False
            if (row["state"] != "CANCEL_REQUESTED"
                    or row["lease_until_ms"] is None
                    or row["lease_until_ms"] > now):
                raise ValueError("Cancellation is not eligible for retirement")
            db.execute("UPDATE jobs SET state='CANCELLED', version=version+1, "
                       "worker=NULL, lease_until_ms=NULL, updated_ms=? "
                       "WHERE request_id=?", (now, request_id))
            self._event(db, request_id, "CANCEL_REQUESTED", "CANCELLED",
                        row["fencing_token"], now)
            return True

    def status(self, request_id: str) -> dict:
        if type(request_id) is not str or not _HEX64.fullmatch(request_id):
            raise ValueError("Invalid request ID")
        with self._connection() as db:
            row = db.execute("SELECT request_id, state, version, fencing_token, "
                             "attempt_no, attempt_id, worker, lease_until_ms "
                             "FROM jobs WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown research request")
            return dict(row)

    def operational_snapshot(self, *, now_ms: int | None = None) -> dict:
        """Read-only control-plane inventory; no claims of execution success.

        An expired RUNNING lease is not proof its worker died. Expose it as
        attention-required, never as automatically recovered or completed.
        """
        now = _now_ms() if now_ms is None else now_ms
        if type(now) is not int or now < 0:
            raise ValueError("Invalid UTC snapshot clock")
        with self._connection() as db:
            rows = db.execute(
                "SELECT state, COUNT(*) AS count FROM jobs GROUP BY state"
            ).fetchall()
            states = {row["state"]: row["count"] for row in rows}
            expired = db.execute(
                "SELECT COUNT(*) FROM jobs "
                "WHERE state IN ('RUNNING', 'RECONCILING', 'CANCEL_REQUESTED') "
                "AND lease_until_ms IS NOT NULL AND lease_until_ms<=?",
                (now,),
            ).fetchone()[0]
            attempts = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            total = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        return {
            "schema": "NRFX_DURABLE_OPERATIONS_SNAPSHOT_V1",
            "status": "CONTROL_PLANE_METADATA_ONLY_NOT_EXECUTION_EVIDENCE",
            "observed_at_ms": now,
            "total_jobs": total,
            "total_attempts": attempts,
            "by_state": dict(sorted(states.items())),
            "expired_active_or_cancel_leases": expired,
            "requires_operator_attention": expired > 0
                or states.get("QUARANTINED", 0) > 0,
            "accepted_results": "NOT_IMPLEMENTED",
            "broker_order_placement_enabled": False,
        }
