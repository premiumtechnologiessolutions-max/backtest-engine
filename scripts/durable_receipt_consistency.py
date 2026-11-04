"""Fail-closed mirror checks for the two engineering-stage receipt formats.

Byte-backed and metadata-only storage must describe the SAME frozen request,
attempt, fence, provider receipt and artifact when both exist. Checks operate
inside the caller's SQLite transaction. No result may become ACCEPTED.
"""
from __future__ import annotations

import hashlib
import json
import re

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_KEYS = ("request_id", "attempt_id", "fencing_token",
         "binding_sha256", "receipt_sha256", "artifact_sha256")


def _hash(value: object) -> None:
    if type(value) is not str or not _HEX64.fullmatch(value):
        raise ValueError("Corrupt mirrored research receipt digest")


def _canonical(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _has_table(db, table: str) -> bool:
    # Only constant internal names may be passed; SQL names cannot be bound.
    if table not in ("unverified_receipts", "external_receipt_inbox"):
        raise ValueError("Unknown receipt storage")
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    ).fetchone() is not None


def metadata_projection(db, attempt_id: str) -> dict | None:
    if not _has_table(db, "unverified_receipts"):
        return None
    rows = db.execute(
        "SELECT * FROM unverified_receipts WHERE attempt_id=?",
        (attempt_id,)
    ).fetchall()
    if len(rows) > 1:
        raise ValueError("Duplicate metadata receipt attempt identity")
    if not rows:
        return None
    row = rows[0]
    try:
        payload = json.loads(row["payload_json"])
        canonical = _canonical(payload)
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("Corrupt metadata mirror JSON") from exc
    if (type(payload) is not dict or type(payload.get("receipt")) is not dict
            or type(row["payload_json"]) is not str
            or len(row["payload_json"].encode("utf-8")) > 16_384
            or row["payload_json"] != canonical
            or hashlib.sha256(canonical.encode("ascii")).hexdigest()
            != row["receipt_sha256"]
            or payload.get("accepted") is not False
            or payload["receipt"].get("accepted") is not False
            or row["fencing_token"] != payload.get("fencing_token")
            or row["request_id"] != payload.get("request_id")
            or row["attempt_id"] != payload.get("attempt_id")):
        raise ValueError("Corrupt metadata receipt mirror")
    projection = {
        "request_id": row["request_id"],
        "attempt_id": row["attempt_id"],
        "fencing_token": row["fencing_token"],
        "binding_sha256": payload.get("binding_sha256"),
        "receipt_sha256": payload["receipt"].get("receipt_sha256"),
        "artifact_sha256": payload.get("actual_artifact_sha256"),
    }
    for key in ("binding_sha256", "receipt_sha256", "artifact_sha256"):
        _hash(projection[key])
    return projection


def byte_projection(db, attempt_id: str) -> dict | None:
    if not _has_table(db, "external_receipt_inbox"):
        return None
    rows = db.execute(
        "SELECT * FROM external_receipt_inbox WHERE attempt_id=?",
        (attempt_id,)
    ).fetchall()
    if len(rows) > 1:
        raise ValueError("Duplicate byte-backed receipt attempt identity")
    if not rows:
        return None
    row = rows[0]
    try:
        binding = json.loads(row["binding_json"])
        receipt = json.loads(row["receipt_json"])
    except (ValueError, TypeError) as exc:
        raise ValueError("Corrupt byte-backed receipt JSON") from exc
    artifact = row["artifact_blob"]
    if (type(binding) is not dict or type(receipt) is not dict
            or receipt.get("accepted") is not False
            or binding.get("result_accepted") is not False
            or row["status"] != "UNVERIFIED_ONLY"
            or _canonical(binding) != row["binding_json"]
            or _canonical(receipt) != row["receipt_json"]
            or type(artifact) is not bytes
            or hashlib.sha256(artifact).hexdigest() != row["artifact_sha256"]
            or receipt.get("artifact_sha256") != row["artifact_sha256"]
            or binding.get("attempt_id") != row["attempt_id"]
            or binding.get("fencing_token") != row["fencing_token"]
            or binding.get("frozen_queue_fingerprint") != row["request_id"]):
        raise ValueError("Corrupt byte-backed receipt mirror")
    projection = {
        "request_id": row["request_id"],
        "attempt_id": row["attempt_id"],
        "fencing_token": row["fencing_token"],
        "binding_sha256": binding.get("binding_sha256"),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "artifact_sha256": row["artifact_sha256"],
    }
    for key in ("binding_sha256", "receipt_sha256", "artifact_sha256"):
        _hash(projection[key])
    return projection


def expect_mirror(existing: dict | None, *, request_id: str,
                  attempt_id: str, fencing_token: int,
                  binding_sha256: str, receipt_sha256: str,
                  artifact_sha256: str) -> None:
    """A one-sided entry is allowed; a mismatched mirror is not."""
    if existing is None:
        return
    wanted = {
        "request_id": request_id, "attempt_id": attempt_id,
        "fencing_token": fencing_token,
        "binding_sha256": binding_sha256,
        "receipt_sha256": receipt_sha256,
        "artifact_sha256": artifact_sha256,
    }
    if existing != wanted:
        raise ValueError("Cross-inbox receipt conflict")


def mirror_inventory(db) -> dict:
    """Count distinct attempts and reject conflicting mirrored records.

    Call only AFTER individual inbox validators have fully authenticated each
    stored receipt and its attempt relationship within this same read snapshot.
    """
    metadata = {}
    backed = {}
    if _has_table(db, "unverified_receipts"):
        for row in db.execute("SELECT attempt_id FROM unverified_receipts"):
            entry = metadata_projection(db, row["attempt_id"])
            if entry is None or entry["attempt_id"] in metadata:
                raise ValueError("Missing or duplicate metadata receipt")
            metadata[entry["attempt_id"]] = entry
    if _has_table(db, "external_receipt_inbox"):
        for row in db.execute("SELECT attempt_id FROM external_receipt_inbox"):
            entry = byte_projection(db, row["attempt_id"])
            if entry is None or entry["attempt_id"] in backed:
                raise ValueError("Missing or duplicate byte-backed receipt")
            backed[entry["attempt_id"]] = entry
    for attempt_id in metadata.keys() & backed.keys():
        if metadata[attempt_id] != backed[attempt_id]:
            raise ValueError("Cross-inbox receipt conflict")
    return {
        "logical_unverified_attempts": len(metadata.keys() | backed.keys()),
        "mirrored_attempts": len(metadata.keys() & backed.keys()),
    }
