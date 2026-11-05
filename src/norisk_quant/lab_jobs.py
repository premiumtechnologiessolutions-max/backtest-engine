"""Durable local job metadata, without execution or market-data authority.

Workers execute only handlers selected by the coordinator. SQLite owns job
identity and fenced state transitions; completion and its result are one atomic
transaction. An expired or cancelled worker cannot publish a result.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time
from typing import Callable

_KIND = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_MAX_JSON = 1_000_000
_STATES = frozenset({"QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"})


class JobStateError(ValueError):
    """The caller no longer owns a live job or requested an invalid transition."""


def _json(value: dict) -> str:
    if type(value) is not dict:
        raise ValueError("A JSON object is required")
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Invalid finite JSON object") from exc
    if len(data.encode("utf-8")) > _MAX_JSON:
        raise ValueError("Job JSON exceeds 1 MB")
    # JSON coercion of non-string keys would make identity ambiguous.
    def check(item):
        if isinstance(item, dict):
            if any(type(key) is not str for key in item):
                raise ValueError("JSON object keys must be strings")
            for val in item.values():
                check(val)
        elif isinstance(item, (list, tuple)):
            for val in item:
                check(val)
    check(value)
    return data


def _worker(value: str) -> str:
    if type(value) is not str or not value or len(value) > 128 or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid bounded worker identity")
    return value


def _lease(value: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not .1 <= value <= 3600:
        raise ValueError("Lease must be between 0.1 and 3600 seconds")
    return float(value)


class JobStore:
    """Single-host SQLite job store; safe for several local worker processes.

    ``clock`` is wall-clock seconds and is injectable for deterministic tests.
    Expired leases are requeued, never implicitly accepted. No daemon starts.
    """

    def __init__(self, db_path: str | Path, *, clock: Callable[[], float] = time.time):
        self.path = Path(db_path)
        if str(db_path) == ":memory:":
            raise ValueError("Durable job storage requires a filesystem database")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        with self._connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS lab_jobs (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload_json TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
                token INTEGER NOT NULL DEFAULT 0, attempt INTEGER NOT NULL DEFAULT 0,
                worker TEXT, lease_until REAL, result_json TEXT, error TEXT,
                created_at REAL NOT NULL, updated_at REAL NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS lab_jobs_ready ON lab_jobs(state, created_at, id)")
            db.execute("""CREATE TABLE IF NOT EXISTS lab_job_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                state TEXT NOT NULL, token INTEGER NOT NULL, observed_at REAL NOT NULL,
                reason TEXT NOT NULL
            )""")

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _transaction(self):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def _now(self):
        value = self.clock()
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid observation clock")
        return float(value)

    @staticmethod
    def _event(db, job_id, state, token, now, reason):
        db.execute("INSERT INTO lab_job_events(job_id,state,token,observed_at,reason) VALUES (?,?,?,?,?)",
                   (job_id, state, token, now, reason))

    @staticmethod
    def _row(db, job_id):
        row = db.execute("SELECT * FROM lab_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("Unknown job")
        return row

    @staticmethod
    def _public(row):
        value = dict(row)
        value["job_id"] = value["id"]
        value["status"] = value["state"]
        value["payload"] = json.loads(value.pop("payload_json"))
        raw_result = value.pop("result_json")
        value["result"] = json.loads(raw_result) if raw_result is not None else None
        return value

    def submit(self, kind: str, payload: dict) -> dict:
        """Deduplicate the exact immutable kind/payload, including terminal jobs."""
        if type(kind) is not str or not _KIND.fullmatch(kind):
            raise ValueError("Invalid job kind")
        encoded = _json(payload)
        ident = hashlib.sha256((kind + "\n" + encoded).encode("utf-8")).hexdigest()
        now = self._now()
        with self._transaction() as db:
            existing = db.execute("SELECT * FROM lab_jobs WHERE id=?", (ident,)).fetchone()
            if existing is None:
                db.execute("""INSERT INTO lab_jobs
                    (id,kind,payload_json,state,created_at,updated_at) VALUES (?,?,?,'QUEUED',?,?)""",
                           (ident, kind, encoded, now, now))
                self._event(db, ident, "QUEUED", 0, now, "submitted")
            return self._public(self._row(db, ident))

    def get(self, job_id: str) -> dict:
        with self._connection() as db:
            return self._public(self._row(db, job_id))

    def list_jobs(self, limit: int = 100) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("List limit must be 1..1000")
        with self._connection() as db:
            rows = db.execute("SELECT * FROM lab_jobs ORDER BY created_at DESC,id LIMIT ?", (limit,))
            return [self._public(row) for row in rows]

    def _recover(self, db, now):
        expired = db.execute("SELECT id,token FROM lab_jobs WHERE state='RUNNING' AND lease_until<=?", (now,)).fetchall()
        for row in expired:
            db.execute("""UPDATE lab_jobs SET state='QUEUED',worker=NULL,lease_until=NULL,
                          updated_at=? WHERE id=?""", (now, row["id"]))
            self._event(db, row["id"], "QUEUED", row["token"], now, "lease_expired")
        return len(expired)

    def recover_expired(self) -> int:
        with self._transaction() as db:
            return self._recover(db, self._now())

    def claim(self, worker: str, lease_seconds: float = 60) -> dict | None:
        worker, lease_seconds = _worker(worker), _lease(lease_seconds)
        now = self._now()
        with self._transaction() as db:
            self._recover(db, now)
            row = db.execute("SELECT * FROM lab_jobs WHERE state='QUEUED' ORDER BY created_at,id LIMIT 1").fetchone()
            if row is None:
                return None
            db.execute("""UPDATE lab_jobs SET state='RUNNING',token=token+1,attempt=attempt+1,
                          worker=?,lease_until=?,updated_at=? WHERE id=?""",
                       (worker, now + lease_seconds, now, row["id"]))
            fresh = self._row(db, row["id"])
            self._event(db, row["id"], "RUNNING", fresh["token"], now, "claimed")
            return self._public(fresh)

    def _owned(self, db, job_id, token, worker, now):
        _worker(worker)
        if type(token) is not int or token < 1:
            raise JobStateError("Invalid fencing token")
        row = self._row(db, job_id)
        if (row["state"] != "RUNNING" or row["token"] != token or row["worker"] != worker
                or row["lease_until"] is None or row["lease_until"] <= now):
            raise JobStateError("Job lease expired, cancelled or owned by another attempt")
        return row

    def heartbeat(self, job_id: str, token: int, worker: str, lease_seconds: float = 60) -> dict:
        lease_seconds, now = _lease(lease_seconds), self._now()
        with self._transaction() as db:
            self._owned(db, job_id, token, worker, now)
            db.execute("UPDATE lab_jobs SET lease_until=?,updated_at=? WHERE id=?", (now+lease_seconds, now, job_id))
            return self._public(self._row(db, job_id))

    def progress(self, job_id: str, token: int, worker: str, stage: str,
                 lease_seconds: float = 60) -> dict:
        """Persist a bounded stage observation under the current fenced lease."""
        if type(stage) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", stage):
            raise ValueError("Stage must contain 1..64 lowercase letters or underscores")
        lease_seconds, now = _lease(lease_seconds), self._now()
        with self._transaction() as db:
            self._owned(db, job_id, token, worker, now)
            db.execute("UPDATE lab_jobs SET lease_until=?,updated_at=? WHERE id=?",
                       (now + lease_seconds, now, job_id))
            self._event(db, job_id, "RUNNING", token, now, "stage:" + stage)
            return self._public(self._row(db, job_id))

    def complete(self, job_id: str, token: int, worker: str, result: dict) -> dict:
        return self._finish(job_id, token, worker, "SUCCEEDED", _json(result), None)

    def fail(self, job_id: str, token: int, worker: str, error: str) -> dict:
        if type(error) is not str or not error or len(error) > 4000:
            raise ValueError("Require a bounded error description")
        return self._finish(job_id, token, worker, "FAILED", None, error)

    def _finish(self, job_id, token, worker, state, result, error):
        now = self._now()
        with self._transaction() as db:
            self._owned(db, job_id, token, worker, now)
            db.execute("""UPDATE lab_jobs SET state=?,result_json=?,error=?,lease_until=NULL,
                          worker=NULL,updated_at=? WHERE id=?""", (state, result, error, now, job_id))
            self._event(db, job_id, state, token, now, "completed" if state == "SUCCEEDED" else "failed")
            return self._public(self._row(db, job_id))

    def cancel(self, job_id: str) -> dict:
        now = self._now()
        with self._transaction() as db:
            row = self._row(db, job_id)
            if row["state"] in {"QUEUED", "RUNNING"}:
                db.execute("""UPDATE lab_jobs SET state='CANCELLED',token=token+1,worker=NULL,
                              lease_until=NULL,updated_at=? WHERE id=?""", (now, job_id))
                self._event(db, job_id, "CANCELLED", row["token"]+1, now, "cancelled")
            return self._public(self._row(db, job_id))

    def events(self, job_id: str) -> list[dict]:
        with self._connection() as db:
            self._row(db, job_id)
            return [dict(row) for row in db.execute("SELECT * FROM lab_job_events WHERE job_id=? ORDER BY seq", (job_id,))]
