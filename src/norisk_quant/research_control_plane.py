"""NoRiskFX Unified Research Control Plane v1 — durable *research-only* queue.

Bridge for AI Quant Lab V4 Nova/Forge hypotheses into canonical XAUUSD
ExperimentIdentity. Does not execute strategy code, talk to MT5, import
datasets, validate evidence, or permit real/paper orders. Deterministic
research intent and SQLite lease fencing prevent duplicate execution claims.

State is private operator data; never expose internal payload/lease tokens
through a browser. This is a bounded SQLite single-site controller, not
a distributed high-availability scheduler.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from hmac import compare_digest
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Iterator

from .registry import ExperimentIdentity, fingerprint

SCHEMA = "NRFX_AIQUANTLAB_HYPOTHESIS_V1"
EXTERNAL_SOURCE = "aiquantlab_institutional_v4"
PROPOSAL_KEYS = frozenset({
    "schema", "producer", "agent", "campaign_id", "asset", "dataset_sha256",
    "engine_commit", "strategy_id", "parameters", "timeframe",
    "window_start_utc", "window_end_exclusive_utc", "quantity_ounces",
    "fee_all_in_per_ounce", "execution_mode", "exposure_context",
})
RESULT_KEYS = frozenset({"disposition", "reason_code", "evidence_sha256"})
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
SLUG = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
PARAM = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")
UTC = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)\Z")
MAX_ACTIVE = 4
MAX_ATTEMPTS = 3


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("Control-plane timestamps require aware UTC datetime")
    return value.astimezone(timezone.utc)


def _clock(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds")


def _iso(value: object, label: str) -> str:
    if type(value) is not str or not UTC.fullmatch(value):
        raise ValueError(f"{label} must be exact UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid {label}") from exc
    return _clock(parsed)


def _sha(value: object, name: str, pattern=HEX64) -> str:
    if type(value) is not str or not pattern.fullmatch(value):
        raise ValueError(f"{name} must be a pinned full hash")
    return value


def _slug(value: object, name: str) -> str:
    if type(value) is not str or not SLUG.fullmatch(value):
        raise ValueError(f"Invalid {name} identifier")
    return value


def _params(raw: object) -> dict[str, int | float]:
    if type(raw) is not dict or len(raw) > 24:
        raise ValueError("Strategy parameters must be bounded flat numeric mapping")
    out = {}
    for key, val in raw.items():
        if type(key) is not str or not PARAM.fullmatch(key):
            raise ValueError("Invalid parameter name")
        if type(val) not in (int, float) or not math.isfinite(val) or abs(val) > 1e6:
            raise ValueError("Parameters cannot contain code, flags or non-finite values")
        out[key] = val
    return out


def proposal_identity(raw: dict) -> tuple[str, str, str]:
    """Return immutable canonical research ID, safe canonical payload, submitter.

    Agent attribution is deliberately EXCLUDED from experiment identity:
    Nova and Forge cannot count the exact same hypothesis as two independent
    tests. Dataset provenance is only *declared* here; a separate verified
    source registry must eventually bind it to original data.
    """
    if type(raw) is not dict or set(raw) != PROPOSAL_KEYS:
        raise ValueError("AI Quant Lab hypothesis schema mismatch; no extras allowed")
    if raw["schema"] != SCHEMA or raw["producer"] != EXTERNAL_SOURCE:
        raise ValueError("Unsupported research producer/schema")
    if raw["agent"] not in ("nova", "forge"):
        raise ValueError("Only Nova/Forge may propose hypotheses, not approve results")
    _slug(raw["campaign_id"], "campaign")
    _slug(raw["strategy_id"], "strategy")
    if raw["asset"] != "XAUUSD":
        raise ValueError("Canonical Gold research accepts XAUUSD only; FX requires separate contracts")
    dataset = _sha(raw["dataset_sha256"], "dataset")
    commit = _sha(raw["engine_commit"], "engine commit", HEX40)
    parameters = _params(raw["parameters"])
    if raw["timeframe"] not in ("M1", "M5", "M15", "H1", "H4", "D1"):
        raise ValueError("Unsupported timeframe")
    if raw["execution_mode"] != "m1_conservative":
        raise ValueError("Only pinned canonical M1 conservative execution is supported")
    if raw["exposure_context"] not in ("training", "historical_exposed"):
        raise ValueError("Agents cannot self-certify future prospective or live evidence")
    if type(raw["quantity_ounces"]) not in (int, float) or not math.isfinite(raw["quantity_ounces"]) or not 0 < raw["quantity_ounces"] <= 100:
        raise ValueError("Invalid bounded research quantity")
    if type(raw["fee_all_in_per_ounce"]) not in (int, float) or raw["fee_all_in_per_ounce"] != 0.40:
        raise ValueError("Canonical research execution requires $0.40/oz all-in")
    start = _iso(raw["window_start_utc"], "window start")
    end = _iso(raw["window_end_exclusive_utc"], "window end")
    if start >= end:
        raise ValueError("Experiment UTC interval must increase")
    identity = ExperimentIdentity(
        dataset_sha256=dataset, engine_commit=commit,
        strategy_id=raw["strategy_id"], parameters=parameters,
        timeframe=raw["timeframe"],
        window_start_utc=start, window_end_exclusive_utc=end,
        quantity_ounces=float(raw["quantity_ounces"]),
        fee_all_in_per_ounce=0.40, execution_mode="m1_conservative",
        exposure_context=raw["exposure_context"],
    )
    # The canonical registry owns deduplication and the cost protocol.
    work_id = fingerprint(identity)
    payload = {
        "canonical_experiment_id": work_id, "dataset_sha256": dataset,
        "engine_commit": commit, "strategy_id": raw["strategy_id"],
        "parameters": parameters, "timeframe": raw["timeframe"],
        "window_start_utc": start, "window_end_exclusive_utc": end,
        "quantity_ounces": float(raw["quantity_ounces"]),
        "fee_all_in_per_ounce": 0.40, "execution_mode": "m1_conservative",
        "exposure_context": raw["exposure_context"],
    }
    return work_id, json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False), raw["agent"]


@dataclass(frozen=True)
class Lease:
    job_id: str
    attempt: int
    token: str
    expires_utc: str

    def __repr__(self) -> str:
        # Avoid accidental console/debug leakage of the random bearer token.
        return f"Lease(job_id={self.job_id[:12]}…, attempt={self.attempt}, token=[REDACTED])"


class ResearchQueue:
    """Transactional, restart-safe local research queue. No strategy runner.

    All state writes occur in BEGIN IMMEDIATE transactions. A lease is
    fenced by a random secret + incrementing attempt number. A crashed worker
    may be reclaimed only after lease expiry; original token becomes invalid.
    Never assume a completed queue task implies a successful backtest.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if self.path.is_symlink() or not self.path.parent.is_dir():
            raise ValueError("Private SQLite path must have a real existing parent")
        if not self.path.exists():
            # Avoid default umask creating a world-readable database on Unix.
            flags = os.O_CREAT | os.O_EXCL | os.O_RDWR
            try:
                fd = os.open(self.path, flags, 0o600)
                os.close(fd)
            except FileExistsError:
                # Concurrent process created it first; next path check applies.
                pass
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("Unsafe research database path")
        with self._transaction() as db:
            # sqlite3.executescript() implicitly COMMITs: that would break
            # our BEGIN IMMEDIATE atomic initialization. Use execute().
            for statement in (
                """CREATE TABLE IF NOT EXISTS research_jobs (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    source_agent TEXT NOT NULL, state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    owner_token_sha256 TEXT, lease_deadline TEXT,
                    created_utc TEXT NOT NULL, updated_utc TEXT NOT NULL,
                    disposition TEXT, reason_code TEXT, evidence_sha256 TEXT
                )""",
                """CREATE TABLE IF NOT EXISTS research_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES research_jobs(id),
                    event_type TEXT NOT NULL,
                    attempt INTEGER NOT NULL, occurred_utc TEXT NOT NULL
                )""",
                """CREATE TABLE IF NOT EXISTS control (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                )""",
                "INSERT OR IGNORE INTO control(key,value) VALUES('paused','1')",
            ):
                db.execute(statement)
        # Intentionally starts PAUSED. Operator must explicitly resume.

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        if self.path.is_symlink():
            raise ValueError("Refusing symlinked research database")
        db = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=20000")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    @staticmethod
    def _event(db: sqlite3.Connection, job_id: str, kind: str,
               attempt: int, now: str) -> None:
        db.execute(
            "INSERT INTO research_events(job_id,event_type,attempt,occurred_utc) VALUES(?,?,?,?)",
            (job_id, kind, attempt, now),
        )

    def submit(self, proposal: dict, *, now: datetime) -> str:
        job_id, canonical, agent = proposal_identity(proposal)
        clock = _clock(now)
        with self._transaction() as db:
            existing = db.execute("SELECT payload FROM research_jobs WHERE id=?", (job_id,)).fetchone()
            if existing:
                if existing["payload"] != canonical:
                    raise ValueError("Canonical experiment ID collision or changed experiment identity")
                return job_id  # no extra event/trial from repeated agent or webhook
            db.execute(
                "INSERT INTO research_jobs(id,payload,source_agent,state,created_utc,updated_utc) "
                "VALUES(?,?,?,'queued',?,?)", (job_id, canonical, agent, clock, clock),
            )
            self._event(db, job_id, "submitted", 0, clock)
        return job_id

    def _expire(self, db: sqlite3.Connection, at: str) -> None:
        for row in db.execute(
            "SELECT id,attempts FROM research_jobs "
            "WHERE state='leased' AND lease_deadline<=? ORDER BY id", (at,),
        ).fetchall():
            exhausted = row["attempts"] >= MAX_ATTEMPTS
            db.execute(
                "UPDATE research_jobs SET state=?, owner_token_sha256=NULL,"
                "lease_deadline=NULL,updated_utc=? WHERE id=?",
                ("exhausted" if exhausted else "queued", at, row["id"]),
            )
            self._event(db, row["id"],
                        "lease_expired_exhausted" if exhausted else "lease_expired_requeued",
                        row["attempts"], at)

    def set_paused(self, paused: bool, *, now: datetime) -> None:
        if type(paused) is not bool:
            raise ValueError("Pause control must be boolean")
        clock = _clock(now)
        with self._transaction() as db:
            old = db.execute("SELECT value FROM control WHERE key='paused'").fetchone()["value"]
            target = "1" if paused else "0"
            if old == target:
                return
            db.execute("UPDATE control SET value=? WHERE key='paused'", (target,))
            if paused:
                # Revoke all in-flight lease tokens immediately.
                for row in db.execute(
                    "SELECT id,attempts FROM research_jobs WHERE state='leased' ORDER BY id"
                ).fetchall():
                    state = "exhausted" if row["attempts"] >= MAX_ATTEMPTS else "queued"
                    db.execute(
                        "UPDATE research_jobs SET state=?,owner_token_sha256=NULL,"
                        "lease_deadline=NULL,updated_utc=? WHERE id=?",
                        (state, clock, row["id"]),
                    )
                    self._event(db, row["id"], "operator_pause_revoked_lease",
                                row["attempts"], clock)

    def claim(self, *, worker: str, now: datetime,
              lease_seconds: int = 120) -> Lease | None:
        _slug(worker, "worker")
        if type(lease_seconds) is not int or not 10 <= lease_seconds <= 3600:
            raise ValueError("Research lease must be between 10 and 3600 seconds")
        clock = _clock(now)
        expire_at = _clock(_utc(now) + timedelta(seconds=lease_seconds))
        with self._transaction() as db:
            if db.execute("SELECT value FROM control WHERE key='paused'").fetchone()["value"] == "1":
                return None
            self._expire(db, clock)
            active = db.execute("SELECT COUNT(*) FROM research_jobs WHERE state='leased'").fetchone()[0]
            if active >= MAX_ACTIVE:
                return None
            row = db.execute(
                "SELECT id,attempts FROM research_jobs WHERE state='queued' "
                "ORDER BY created_utc,id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            attempt = row["attempts"] + 1
            if attempt > MAX_ATTEMPTS:
                raise ValueError("Research queue attempt budget corrupted")
            token = secrets.token_hex(32)
            db.execute(
                "UPDATE research_jobs SET state='leased', attempts=?,"
                "owner_token_sha256=?, lease_deadline=?, updated_utc=? WHERE id=?",
                (attempt, sha256(token.encode("ascii")).hexdigest(),
                 expire_at, clock, row["id"]),
            )
            self._event(db, row["id"], "claimed", attempt, clock)
            return Lease(row["id"], attempt, token, expire_at)

    @staticmethod
    def _check_lease(db: sqlite3.Connection, lease: Lease, at: str) -> sqlite3.Row | None:
        if not isinstance(lease, Lease):
            raise ValueError("Lease object required")
        row = db.execute("SELECT * FROM research_jobs WHERE id=?", (lease.job_id,)).fetchone()
        if row is None or row["state"] != "leased" or row["attempts"] != lease.attempt:
            return None
        stored = row["owner_token_sha256"]
        if type(stored) is not str or not compare_digest(stored, sha256(lease.token.encode("ascii")).hexdigest()):
            return None
        if row["lease_deadline"] <= at:
            return None
        return row

    def heartbeat(self, lease: Lease, *, now: datetime, extend_seconds: int = 120) -> bool:
        if type(extend_seconds) is not int or not 10 <= extend_seconds <= 3600:
            raise ValueError("Invalid lease extension")
        now_utc = _clock(now)
        until = _clock(_utc(now) + timedelta(seconds=extend_seconds))
        with self._transaction() as db:
            if db.execute("SELECT value FROM control WHERE key='paused'").fetchone()["value"] == "1":
                return False
            if self._check_lease(db, lease, now_utc) is None:
                return False
            db.execute(
                "UPDATE research_jobs SET lease_deadline=?,updated_utc=? WHERE id=?",
                (until, now_utc, lease.job_id),
            )
            self._event(db, lease.job_id, "heartbeat", lease.attempt, now_utc)
            return True

    def finish(self, lease: Lease, *, now: datetime, result: dict) -> bool:
        """Record unverified artifact reference; never accept success metrics."""
        if type(result) is not dict or set(result) != RESULT_KEYS:
            raise ValueError("Result may only contain disposition, reason and evidence SHA")
        disposition = result["disposition"]
        if disposition not in ("proposal_recorded", "rejected"):
            raise ValueError("Queue cannot certify successful strategies or live execution")
        _slug(result["reason_code"], "reason")
        evidence = result["evidence_sha256"]
        if evidence is not None:
            _sha(evidence, "artifact evidence")
        elif disposition == "proposal_recorded":
            raise ValueError("A recorded proposal must have an immutable evidence hash")
        at = _clock(now)
        with self._transaction() as db:
            if db.execute("SELECT value FROM control WHERE key='paused'").fetchone()["value"] == "1":
                return False
            row = self._check_lease(db, lease, at)
            if row is None:
                return False
            state = "rejected" if disposition == "rejected" else "completed"
            db.execute(
                "UPDATE research_jobs SET state=?,disposition=?,reason_code=?,"
                "evidence_sha256=?,owner_token_sha256=NULL,lease_deadline=NULL,"
                "updated_utc=? WHERE id=?",
                (state, disposition, result["reason_code"], evidence, at, lease.job_id),
            )
            self._event(db, lease.job_id,
                        "research_artifact_recorded" if state == "completed" else "proposal_rejected",
                        lease.attempt, at)
            return True

    def status(self, job_id: str) -> dict:
        _sha(job_id, "job")
        with self._transaction() as db:
            row = db.execute("SELECT * FROM research_jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            return {
                "experiment_id": row["id"], "state": row["state"],
                "source_agent": row["source_agent"], "attempts": row["attempts"],
                "created_utc": row["created_utc"], "updated_utc": row["updated_utc"],
                "execution": "NONE",
                "profitability_verified": False,
                "independent_oos": False,
                "risk_approved": False,
                "research_only": True,
            }

    def audit(self, job_id: str) -> tuple[dict, ...]:
        _sha(job_id, "job")
        with self._transaction() as db:
            return tuple(
                dict(event_type=row["event_type"], attempt=row["attempt"],
                     occurred_utc=row["occurred_utc"])
                for row in db.execute(
                    "SELECT event_type,attempt,occurred_utc FROM research_events "
                    "WHERE job_id=? ORDER BY seq", (job_id,),
                )
            )

    def counts(self) -> dict[str, int | bool]:
        with self._transaction() as db:
            counts = {key: 0 for key in
                      ("queued", "leased", "completed", "rejected", "exhausted")}
            for row in db.execute("SELECT state,COUNT(*) AS total FROM research_jobs GROUP BY state"):
                counts[row["state"]] = row["total"]
            counts["paused"] = db.execute(
                "SELECT value FROM control WHERE key='paused'"
            ).fetchone()["value"] == "1"
            return counts
