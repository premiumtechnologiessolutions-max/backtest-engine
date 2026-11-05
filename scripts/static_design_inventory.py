"""Read-only, fail-closed summary for static adapter design inventory.

This is NOT a research result or an execution authorization. Never returns
stored envelopes, strategy payloads, or executable job identifiers.
"""
from __future__ import annotations

import hashlib
import json

from scripts.durable_research_state import DurableResearchState
from scripts.durable_static_adapter_designs import _audit, SCHEMA


def inspect_static_design_inventory(state: DurableResearchState) -> dict:
    """Audit and fingerprint the inventory in one read transaction.

    An absent inbox is empty; a partially created or damaged inbox fails
    closed. No DDL, workers, network calls or job mutations are performed.
    """
    if not isinstance(state, DurableResearchState):
        raise ValueError("Expected durable state store")
    with state._connection() as db:
        db.execute("BEGIN")
        tables = {
            row["name"] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('static_adapter_designs','static_adapter_request_ids')"
            )
        }
        if not tables:
            summary = {"schema": SCHEMA, "batches": 0, "requests": 0}
            identifiers = []
        else:
            # _audit rejects missing counterpart, schema drift, orphan FKs,
            # mutated manifests, unauthorized states, and incomplete indexes.
            summary = _audit(db)
            identifiers = [
                row["batch_sha256"] for row in db.execute(
                    "SELECT batch_sha256 FROM static_adapter_designs "
                    "ORDER BY batch_sha256"
                )
            ]
        canonical = json.dumps(
            identifiers, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        return {
            "schema": "NRFX_STATIC_DESIGN_INVENTORY_V1",
            "design_schema": SCHEMA,
            "batches": summary["batches"],
            "requests": summary["requests"],
            "inventory_sha256": hashlib.sha256(canonical).hexdigest(),
            "execution_authorized": False,
            "results_verified": False,
            "jobs_created": 0,
        }

def snapshot_static_design_records(state: DurableResearchState) -> list[dict]:
    """Read-only audited envelope fingerprints; not provenance or research proof."""
    if not isinstance(state, DurableResearchState):
        raise ValueError("Expected durable state store")
    with state._connection() as db:
        db.execute("BEGIN")
        tables = {row["name"] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('static_adapter_designs','static_adapter_request_ids')"
        )}
        if not tables:
            return []
        # Reject a partial schema before COUNT queries; preserve the public
        # fail-closed ValueError contract instead of leaking sqlite errors.
        if tables != {"static_adapter_designs", "static_adapter_request_ids"}:
            raise ValueError("Incomplete static design inbox schema")
        # Bound rows before _audit materializes all batches and request IDs.
        # The audit itself uses fetchall(), so a post-audit guard alone cannot
        # protect against oversized or maliciously expanded inboxes.
        request_count = db.execute(
            "SELECT COUNT(*) FROM static_adapter_request_ids"
        ).fetchone()[0]
        batch_count = db.execute(
            "SELECT COUNT(*) FROM static_adapter_designs"
        ).fetchone()[0]
        if request_count > 10000 or batch_count > 10000:
            raise ValueError("Static design snapshot exceeds continuity limit")
        summary = _audit(db)
        # Match the continuity verifier bound before decoding stored envelopes.
        # A valid but oversized inbox must fail closed rather than exhaust memory.
        if summary["requests"] > 10000:
            raise ValueError("Static design snapshot exceeds continuity limit")
        records = []
        for batch in db.execute(
            "SELECT batch_sha256,envelopes_json FROM static_adapter_designs "
            "ORDER BY batch_sha256"
        ):
            for envelope in json.loads(batch["envelopes_json"]):
                canonical = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=True, allow_nan=False).encode("ascii")
                records.append({
                    "batch_id": batch["batch_sha256"],
                    "request_id": envelope["request_id"],
                    "payload_sha256": hashlib.sha256(canonical).hexdigest(),
                })
        if len(records) != summary["requests"]:
            raise ValueError("Static design snapshot count mismatch")
        return sorted(records, key=lambda row: (row["batch_id"], row["request_id"]))
