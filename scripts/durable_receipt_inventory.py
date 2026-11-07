"""Read-only integrity inventory across both legacy metadata and byte-backed inboxes.

ENGINEERING ONLY: neither staging format is equivalent to independent research
acceptance. Metadata-only receipts contain caller-declared artifact hashes,
not independently observed bytes. Both stores must be visible to watchdogs.
"""
from __future__ import annotations

import hashlib
import json
import re

from norisk_quant.external_research_bridge import SCHEMA as EXTERNAL_SCHEMA
from scripts.durable_external_receipts import audit_staged_external_receipts
from scripts.durable_research_state import DurableResearchState
from scripts.research_job_queue import _verify

SCHEMA = "NRFX_COMBINED_EXTERNAL_RECEIPT_AUDIT_V1"
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _require_hash(value: object) -> None:
    if type(value) is not str or not _HEX64.fullmatch(value):
        raise ValueError("Invalid stored external receipt digest")


def _legacy_rows(db) -> int:
    exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='unverified_receipts'"
    ).fetchone()
    if exists is None:
        return 0
    rows = db.execute(
        "SELECT r.*, a.request_id AS attempt_request, "
        "a.fencing_token AS attempt_token, j.frozen_json "
        "FROM unverified_receipts r "
        "LEFT JOIN attempts a ON a.attempt_id=r.attempt_id "
        "LEFT JOIN jobs j ON j.request_id=r.request_id "
        "ORDER BY r.request_id, r.attempt_id"
    ).fetchall()
    for row in rows:
        if (row["attempt_request"] != row["request_id"]
                or row["attempt_token"] != row["fencing_token"]
                or type(row["frozen_json"]) is not str
                or type(row["payload_json"]) is not str
                or len(row["payload_json"].encode()) > 16_384):
            raise ValueError("Disconnected or oversized metadata receipt")
        try:
            record = json.loads(row["frozen_json"])
            payload = json.loads(row["payload_json"])
        except (ValueError, TypeError) as exc:
            raise ValueError("Corrupt metadata receipt JSON") from exc
        if type(record) is not dict or type(payload) is not dict:
            raise ValueError("Invalid metadata receipt records")
        _verify(record, row["request_id"] + ".json")
        expected = {
            "schema", "request_id", "attempt_id", "fencing_token",
            "binding_sha256", "receipt", "actual_artifact_sha256",
            "accepted",
        }
        if (set(payload) != expected
                or payload["schema"] != "NRFX_UNVERIFIED_RECEIPT_INBOX_V1"
                or payload["accepted"] is not False
                or payload["request_id"] != row["request_id"]
                or payload["attempt_id"] != row["attempt_id"]
                or payload["fencing_token"] != row["fencing_token"]):
            raise ValueError("Metadata receipt identity or approval tampering")
        _require_hash(payload["binding_sha256"])
        _require_hash(payload["actual_artifact_sha256"])
        _require_hash(row["receipt_sha256"])
        raw = _canonical(payload)
        if (raw.decode("ascii") != row["payload_json"]
                or hashlib.sha256(raw).hexdigest() != row["receipt_sha256"]):
            raise ValueError("Stored metadata receipt digest mismatch")
        receipt = payload["receipt"]
        fields = {"schema", "kind", "request_sha256", "engine",
                  "provider_build_sha256", "artifact_sha256", "status",
                  "accepted", "receipt_sha256"}
        if (type(receipt) is not dict or set(receipt) != fields
                or receipt["schema"] != EXTERNAL_SCHEMA
                or receipt["kind"] != "external_result_receipt"
                or receipt["status"] not in {"completed_unverified", "failed"}
                or receipt["accepted"] is not False
                or receipt["artifact_sha256"] != payload["actual_artifact_sha256"]):
            raise ValueError("Unsafe provider-declared metadata receipt")
        for field in ("request_sha256", "provider_build_sha256",
                      "artifact_sha256", "receipt_sha256"):
            _require_hash(receipt[field])
        recomputed = hashlib.sha256(
            _canonical({k: v for k, v in receipt.items()
                        if k != "receipt_sha256"})
        ).hexdigest()
        if receipt["receipt_sha256"] != recomputed:
            raise ValueError("Provider receipt internal digest mismatch")
    return len(rows)


def audit_all_external_receipts(store: DurableResearchState) -> dict:
    """Inspect both inboxes without writing or changing job state.

    The operational gate passes its shared WAL read transaction through
    DurableResearchState._connection so audit and state inventory agree.
    """
    with store._connection() as db:
        metadata_only = _legacy_rows(db)
        evidence = audit_staged_external_receipts(store)
        from scripts.durable_receipt_consistency import mirror_inventory
        mirrors = mirror_inventory(db)
    count = metadata_only + evidence["unverified_receipts"]
    return {
        "schema": SCHEMA,
        "unverified_receipts": count,
        "metadata_only_unverified": metadata_only,
        "byte_backed_unverified": evidence["unverified_receipts"],
        "accepted_results": 0,
        "logical_unverified_attempts": mirrors["logical_unverified_attempts"],
        "mirrored_attempts": mirrors["mirrored_attempts"],
        "operator_attention": count > 0,
    }
