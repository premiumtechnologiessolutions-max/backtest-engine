"""Quarantined receipt inbox for synthetic/offline engineering contracts.

This module stores only unverified metadata. It cannot launch research, read
market data, or transition any job to ACCEPTED. A future independent validator
must implement acceptance as a separate reviewed operation.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

from norisk_quant.external_queue_binding import bind_unverified_receipt
from scripts.durable_research_state import DurableResearchState, _now_ms

MAX_RECEIPT_BYTES = 16384


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


class UnverifiedReceiptInbox:
    """Transactional, immutable receipt staging in an existing durable DB."""

    def __init__(self, state: DurableResearchState):
        self.state = state
        with self.state._write() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS unverified_receipts ("
                "request_id TEXT NOT NULL REFERENCES jobs(request_id), "
                "attempt_id TEXT NOT NULL, fencing_token INTEGER NOT NULL, "
                "receipt_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, "
                "created_ms INTEGER NOT NULL, "
                "PRIMARY KEY (request_id, attempt_id))"
            )

    def stage(self, record: dict, claim: dict, binding: dict,
              receipt: dict, *, actual_artifact_sha256: str,
              now_ms: int | None = None) -> dict:
        """Atomically stage verified *identity*, not verified trading evidence.

        Lease checks occur inside the same write transaction as publication.
        Repeated identical submissions are idempotent only while the claim is
        still live. A different payload for the same attempt is rejected.
        """
        verified = bind_unverified_receipt(
            record, claim, binding, receipt,
            actual_artifact_sha256=actual_artifact_sha256,
        )
        now = _now_ms() if now_ms is None else now_ms
        if type(now) is not int or now < 0:
            raise ValueError("Invalid UTC receipt clock")
        payload = {
            "schema": "NRFX_UNVERIFIED_RECEIPT_INBOX_V1",
            "request_id": claim["request_id"],
            "attempt_id": claim["attempt_id"],
            "fencing_token": claim["fencing_token"],
            "binding_sha256": verified["binding_sha256"],
            "receipt": receipt,
            "actual_artifact_sha256": actual_artifact_sha256,
            "accepted": False,
        }
        encoded = _canonical(payload)
        if len(encoded) > MAX_RECEIPT_BYTES:
            raise ValueError("Oversized receipt")
        digest = hashlib.sha256(encoded).hexdigest()
        with self.state._write() as db:
            row = self.state._owned(
                db, claim["request_id"], claim["attempt_id"],
                claim["fencing_token"], claim["worker"], now,
            )
            if row["state"] != "RECONCILING":
                raise ValueError("Receipt requires RECONCILING state")
            from scripts.durable_receipt_consistency import (
                byte_projection, expect_mirror,
            )
            expect_mirror(
                byte_projection(db, claim["attempt_id"]),
                request_id=claim["request_id"], attempt_id=claim["attempt_id"],
                fencing_token=claim["fencing_token"],
                binding_sha256=verified["binding_sha256"],
                receipt_sha256=receipt["receipt_sha256"],
                artifact_sha256=actual_artifact_sha256,
            )
            existing = db.execute(
                "SELECT receipt_sha256, payload_json FROM unverified_receipts "
                "WHERE request_id=? AND attempt_id=?",
                (claim["request_id"], claim["attempt_id"]),
            ).fetchone()
            if existing is not None:
                if (existing["receipt_sha256"] != digest
                        or existing["payload_json"] != encoded.decode("ascii")):
                    raise ValueError("Immutable receipt content drift")
            else:
                db.execute(
                    "INSERT INTO unverified_receipts "
                    "(request_id, attempt_id, fencing_token, receipt_sha256, "
                    "payload_json, created_ms) VALUES (?, ?, ?, ?, ?, ?)",
                    (claim["request_id"], claim["attempt_id"],
                     claim["fencing_token"], digest, encoded.decode("ascii"), now),
                )
        return {"status": "STAGED_UNVERIFIED", "accepted": False,
                "receipt_sha256": digest}

    def inspect(self, request_id: str, attempt_id: str) -> dict:
        """Read staged metadata with a digest check; never imply acceptance."""
        with self.state._connection() as db:
            row = db.execute(
                "SELECT payload_json, receipt_sha256 FROM unverified_receipts "
                "WHERE request_id=? AND attempt_id=?", (request_id, attempt_id),
            ).fetchone()
            if row is None:
                raise ValueError("Unknown staged receipt")
            raw = row["payload_json"].encode("ascii")
            if hashlib.sha256(raw).hexdigest() != row["receipt_sha256"]:
                raise ValueError("Stored receipt digest mismatch")
            value = json.loads(raw)
            if (value.get("accepted") is not False
                    or _canonical(value) != raw):
                raise ValueError("Unsafe stored receipt")
            return value
