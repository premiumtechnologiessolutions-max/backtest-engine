"""Transactional receipt inbox for the frozen durable research control plane.

ENGINEERING ONLY. Stages bounded, synthetic-compatible external evidence
without running a provider, backtest, worker or live trade. A provider receipt
is NOT independent accounting evidence, OOS proof, or an accepted result.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time

from norisk_quant.external_queue_binding import verify_binding
from norisk_quant.external_research_bridge import verify_result
from scripts.durable_research_state import DurableResearchState

SCHEMA = "NRFX_DURABLE_EXTERNAL_RECEIPT_INBOX_V1"
MAX_ARTIFACT_BYTES = 1_048_576
MAX_METADATA_BYTES = 32_768


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _utc_ms(now_ms: int | None) -> int:
    now = time.time_ns() // 1_000_000 if now_ms is None else now_ms
    if type(now) is not int or now < 0:
        raise ValueError("Invalid receipt clock")
    return now


def _artifact(data: bytes) -> str:
    if type(data) is not bytes or not 1 <= len(data) <= MAX_ARTIFACT_BYTES:
        raise ValueError("External evidence must be bounded nonempty bytes")
    return hashlib.sha256(data).hexdigest()


def _ensure_table(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS external_receipt_inbox ("
        "attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id), "
        "request_id TEXT NOT NULL REFERENCES jobs(request_id), "
        "fencing_token INTEGER NOT NULL, "
        "binding_json TEXT NOT NULL, receipt_json TEXT NOT NULL, "
        "artifact_sha256 TEXT NOT NULL, artifact_blob BLOB NOT NULL, "
        "staged_ms INTEGER NOT NULL, "
        "status TEXT NOT NULL CHECK(status='UNVERIFIED_ONLY'), "
        "UNIQUE(request_id, fencing_token))"
    )


def stage_external_receipt(
    store: DurableResearchState, record: dict, claim: dict,
    binding: dict, receipt: dict, *, artifact_bytes: bytes,
    now_ms: int | None = None,
) -> dict:
    """Atomically stage bytes only from a currently leased RECONCILING attempt.

    A failed transaction cannot expose a partial receipt. Repeat is permitted
    solely for identical bytes/metadata, while the lease remains valid.
    Worker/cancel/expiry/fencing checks are repeated INSIDE the write lock.
    """
    if not isinstance(store, DurableResearchState):
        raise ValueError("Expected existing durable research store")
    now = _utc_ms(now_ms)
    digest = _artifact(artifact_bytes)
    frozen_binding = verify_binding(record, claim, binding)
    frozen_receipt = verify_result(
        frozen_binding["external_request"], receipt,
        actual_artifact_sha256=digest)
    binding_json, receipt_json = (
        _canonical(frozen_binding), _canonical(frozen_receipt))
    if max(len(binding_json.encode()), len(receipt_json.encode())) > MAX_METADATA_BYTES:
        raise ValueError("Oversized receipt metadata")
    request_id = record["fingerprint"]
    attempt_id = claim["attempt_id"]
    token = claim["fencing_token"]
    worker = claim["worker"]

    with store._write() as db:
        owner = store._owned(db, request_id, attempt_id, token, worker, now)
        if owner["state"] != "RECONCILING":
            raise ValueError("Only an active reconciling attempt can stage evidence")
        if owner["attempt_no"] != claim["attempt_no"]:
            raise ValueError("Attempt number drift")
        if owner["frozen_json"] != _canonical(record):
            raise ValueError("Durable frozen queue record drift")
        attempt = db.execute(
            "SELECT request_id, attempt_no, fencing_token, worker "
            "FROM attempts WHERE attempt_id=?", (attempt_id,)
        ).fetchone()
        if attempt is None or any((
            attempt["request_id"] != request_id,
            attempt["attempt_no"] != claim["attempt_no"],
            attempt["fencing_token"] != token,
            attempt["worker"] != worker,
        )):
            raise ValueError("Durable attempt history drift")
        _ensure_table(db)
        prior = db.execute(
            "SELECT * FROM external_receipt_inbox WHERE attempt_id=?",
            (attempt_id,)
        ).fetchone()
        if prior is not None:
            if not (
                prior["request_id"] == request_id
                and prior["fencing_token"] == token
                and prior["binding_json"] == binding_json
                and prior["receipt_json"] == receipt_json
                and prior["artifact_sha256"] == digest
                and prior["artifact_blob"] == artifact_bytes
                and prior["status"] == "UNVERIFIED_ONLY"
            ):
                raise ValueError("Immutable external receipt conflict")
            status = "ALREADY_STAGED_UNVERIFIED"
        else:
            db.execute(
                "INSERT INTO external_receipt_inbox("
                "attempt_id, request_id, fencing_token, binding_json, "
                "receipt_json, artifact_sha256, artifact_blob, "
                "staged_ms, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, "
                "'UNVERIFIED_ONLY')",
                (attempt_id, request_id, token, binding_json, receipt_json,
                 digest, artifact_bytes, now),
            )
            status = "STAGED_UNVERIFIED"
    return {
        "schema": SCHEMA, "status": status, "request_id": request_id,
        "attempt_id": attempt_id, "fencing_token": token,
        "artifact_sha256": digest, "receipt_sha256": frozen_receipt["receipt_sha256"],
        "accepted": False, "broker_execution_authorized": False,
    }


def _validate_staged(db: sqlite3.Connection, attempt_id: str) -> dict:
    row = db.execute(
        "SELECT r.*, a.attempt_no AS history_attempt_no, "
        "a.fencing_token AS history_fencing_token, "
        "a.worker AS history_worker, j.frozen_json "
        "FROM external_receipt_inbox r "
        "JOIN attempts a ON a.attempt_id=r.attempt_id "
        "JOIN jobs j ON j.request_id=r.request_id "
        "WHERE r.attempt_id=?", (attempt_id,)
    ).fetchone()
    if row is None:
        raise ValueError("Unknown or disconnected external receipt")
    if (row["status"] != "UNVERIFIED_ONLY"
            or row["history_fencing_token"] != row["fencing_token"]
            or not isinstance(row["artifact_blob"], bytes)
            or not 1 <= len(row["artifact_blob"]) <= MAX_ARTIFACT_BYTES):
        raise ValueError("Corrupted external receipt/attempt linkage")
    raw_digest = _artifact(row["artifact_blob"])
    if raw_digest != row["artifact_sha256"]:
        raise ValueError("External receipt evidence digest drift")
    try:
        record = json.loads(row["frozen_json"])
        binding = json.loads(row["binding_json"])
        receipt = json.loads(row["receipt_json"])
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        raise ValueError("Corrupted frozen receipt JSON") from exc
    if (type(record) is not dict or type(binding) is not dict
            or type(receipt) is not dict
            or row["binding_json"] != _canonical(binding)
            or row["receipt_json"] != _canonical(receipt)):
        raise ValueError("Noncanonical frozen receipt")
    if (row["request_id"] != record.get("fingerprint")
            or row["history_attempt_no"] != binding.get("attempt_no")
            or row["history_worker"] != binding.get("worker")):
        raise ValueError("Receipt durable attempt identity drift")
    claim = {
        "request_id": row["request_id"],
        "attempt_id": attempt_id,
        "attempt_no": row["history_attempt_no"],
        "fencing_token": row["fencing_token"],
        "worker": row["history_worker"],
        "frozen_request": record,
    }
    canonical_binding = verify_binding(record, claim, binding)
    canonical_receipt = verify_result(
        canonical_binding["external_request"], receipt,
        actual_artifact_sha256=raw_digest)
    if canonical_receipt != receipt:
        raise ValueError("External receipt integrity mismatch")
    return {
        "schema": SCHEMA, "status": "UNVERIFIED_ONLY",
        "attempt_id": attempt_id, "request_id": row["request_id"],
        "fencing_token": row["fencing_token"],
        "binding_sha256": canonical_binding["binding_sha256"],
        "receipt_sha256": canonical_receipt["receipt_sha256"],
        "artifact_sha256": raw_digest,
        "artifact_bytes": row["artifact_blob"],
        "accepted": False,
    }


def read_staged_external_receipt(store: DurableResearchState,
                                 attempt_id: str) -> dict:
    """Locally retrieve the exact persisted bytes for later independent audit.

    Historical attempts may be inspected even after fencing/requeue, but
    reading a receipt never confers current lease ownership or acceptance.
    """
    if type(attempt_id) is not str or not len(attempt_id) == 32 or any(
        c not in "0123456789abcdef" for c in attempt_id
    ):
        raise ValueError("Invalid receipt attempt identity")
    with store._connection() as db:
        return _validate_staged(db, attempt_id)


def audit_staged_external_receipts(store: DurableResearchState) -> dict:
    """Verify every stored receipt, for the read-only operational gate.

    Uses the connection supplied by DurableResearchState; that may be the
    gate's single pinned SQLite read transaction. No receipt is accepted.
    """
    with store._connection() as db:
        exists = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='external_receipt_inbox'"
        ).fetchone()
        if exists is None:
            return {"schema": SCHEMA, "unverified_receipts": 0,
                    "accepted_results": 0}
        attempt_ids = [
            row[0] for row in db.execute(
                "SELECT attempt_id FROM external_receipt_inbox ORDER BY attempt_id"
            )
        ]
        for attempt_id in attempt_ids:
            _validate_staged(db, attempt_id)
    return {"schema": SCHEMA, "unverified_receipts": len(attempt_ids),
            "accepted_results": 0}
