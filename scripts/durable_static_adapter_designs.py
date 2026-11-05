"""Durable, inert adapter-design manifest inbox.

Independent of the executable research queue by construction. Stores only
validated schema field names and disabled design receipts. Never imports an
adapter runtime, stages a job, starts a worker or authorizes research.
"""
from __future__ import annotations

import hashlib
import json

from scripts.durable_research_state import DurableResearchState
from scripts.static_adapter_batch_manifest import (
    make_static_batch_manifest, validate_static_batch_manifest,
)

SCHEMA = "NRFX_DURABLE_STATIC_ADAPTER_DESIGNS_V1"
_MAX_BYTES = 65536


def _encoded(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _schema(db) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS static_adapter_designs ("
        "batch_sha256 TEXT PRIMARY KEY, manifest_json TEXT NOT NULL,"
        "envelopes_json TEXT NOT NULL, state TEXT NOT NULL "
        "CHECK(state='DESIGN_ONLY_DISABLED'))"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS static_adapter_request_ids ("
        "request_id TEXT PRIMARY KEY, batch_sha256 TEXT NOT NULL "
        "REFERENCES static_adapter_designs(batch_sha256))"
    )


def _verify_table_contract(db) -> None:
    """Refuse schema downgrades, even if all current rows look valid.

    A damaged table recreated without PRIMARY KEY / CHECK / REFERENCES
    can otherwise pass row-by-row audits until a later write. This check
    performs only read-only SQLite introspection, never a repair.
    """
    expected = {
        "static_adapter_designs": [
            ("batch_sha256", "TEXT", 0, 1),
            ("manifest_json", "TEXT", 1, 0),
            ("envelopes_json", "TEXT", 1, 0),
            ("state", "TEXT", 1, 0),
        ],
        "static_adapter_request_ids": [
            ("request_id", "TEXT", 0, 1),
            ("batch_sha256", "TEXT", 1, 0),
        ],
    }
    for table, columns in expected.items():
        info = db.execute(f"PRAGMA table_info({table})").fetchall()
        actual = [(row["name"], row["type"].upper(),
                   row["notnull"], row["pk"]) for row in info]
        if actual != columns:
            raise ValueError("Static design table schema drift")
        record = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if record is None or type(record["sql"]) is not str:
            raise ValueError("Missing static design table definition")
        # The exact DDL is part of this application's private store contract.
        # Normalization tolerates case/whitespace, not missing constraints.
        import re
        ddl = re.sub(r"\\s+", "", record["sql"]).upper()
        if table == "static_adapter_designs":
            if "CHECK(STATE='DESIGN_ONLY_DISABLED')" not in ddl:
                raise ValueError("Static design disabled-only CHECK constraint missing")
        elif ("REFERENCESSTATIC_ADAPTER_DESIGNS(BATCH_SHA256)" not in ddl):
            raise ValueError("Static design request foreign key missing")
    fk = db.execute("PRAGMA foreign_key_list(static_adapter_request_ids)").fetchall()
    if len(fk) != 1 or (
        fk[0]["table"], fk[0]["from"], fk[0]["to"]
    ) != ("static_adapter_designs", "batch_sha256", "batch_sha256"):
        raise ValueError("Static design request foreign key drift")


def _audit(db) -> dict:
    """Verify existing storage without DDL or silently repairing damage."""
    required = {"static_adapter_designs", "static_adapter_request_ids"}
    existing = {
        row["name"] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('static_adapter_designs','static_adapter_request_ids')"
        ).fetchall()
    }
    if existing != required:
        raise ValueError("Incomplete static design tables; refusing implicit repair")
    _verify_table_contract(db)
    batches = db.execute(
        "SELECT * FROM static_adapter_designs ORDER BY batch_sha256"
    ).fetchall()
    indexed = db.execute(
        "SELECT request_id,batch_sha256 FROM static_adapter_request_ids "
        "ORDER BY request_id"
    ).fetchall()
    expected_index = {}
    for row in batches:
        raw_manifest, raw_envelopes = row["manifest_json"], row["envelopes_json"]
        if (type(raw_manifest) is not str or type(raw_envelopes) is not str
                or len(raw_manifest.encode("utf-8")) > _MAX_BYTES
                or len(raw_envelopes.encode("utf-8")) > _MAX_BYTES
                or row["state"] != "DESIGN_ONLY_DISABLED"):
            raise ValueError("Corrupt or privileged static design storage")
        try:
            manifest = json.loads(raw_manifest)
            envelopes = json.loads(raw_envelopes)
            validated = validate_static_batch_manifest(envelopes, manifest)
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ValueError("Corrupt static design manifest") from exc
        if (raw_manifest != _encoded(validated)
                or raw_envelopes != _encoded(envelopes)
                or row["batch_sha256"] != validated["manifest_sha256"]):
            raise ValueError("Noncanonical or mutated static design manifest")
        for request_id in validated["request_ids"]:
            if request_id in expected_index:
                raise ValueError("Reused static request ID across batches")
            expected_index[request_id] = row["batch_sha256"]
    observed_index = [(r["request_id"], r["batch_sha256"]) for r in indexed]
    if observed_index != sorted(expected_index.items()):
        raise ValueError("Static design request index is incomplete or tampered")
    return {
        "schema": SCHEMA, "batches": len(batches),
        "requests": len(expected_index), "state": "DESIGN_ONLY_DISABLED",
        "execution_authorized": False, "results_verified": False,
        "jobs_created": 0,
    }


def stage_static_adapter_designs(state: DurableResearchState,
                                 envelopes: object) -> dict:
    """Atomically stage one complete batch, idempotently, without queue access.

    Duplicate IDs across different batches are refused, including if another
    writer races to stage them. Existing damaged rows fail closed.
    """
    if not isinstance(state, DurableResearchState):
        raise ValueError("Expected durable state store")
    manifest = make_static_batch_manifest(envelopes)
    encoded_manifest = _encoded(manifest)
    encoded_envelopes = _encoded(envelopes)
    if (len(encoded_manifest.encode("utf-8")) > _MAX_BYTES
            or len(encoded_envelopes.encode("utf-8")) > _MAX_BYTES):
        raise ValueError("Oversized static design batch")
    with state._write() as db:
        existing = {
            row["name"] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('static_adapter_designs','static_adapter_request_ids')"
            ).fetchall()
        }
        if existing and existing != {"static_adapter_designs", "static_adapter_request_ids"}:
            raise ValueError("Incomplete static design tables; refusing implicit repair")
        if not existing:
            _schema(db)
        _audit(db)
        current = db.execute(
            "SELECT manifest_json,envelopes_json FROM static_adapter_designs "
            "WHERE batch_sha256=?", (manifest["manifest_sha256"],)
        ).fetchone()
        if current is not None:
            if (current["manifest_json"] != encoded_manifest
                    or current["envelopes_json"] != encoded_envelopes):
                raise ValueError("Static design hash collision or content drift")
            status = "ALREADY_STAGED_DESIGN_ONLY"
        else:
            ids = manifest["request_ids"]
            placeholders = ",".join("?" for _ in ids)
            if db.execute(
                f"SELECT 1 FROM static_adapter_request_ids "
                f"WHERE request_id IN ({placeholders}) LIMIT 1", ids
            ).fetchone():
                raise ValueError("Static request ID already belongs to another batch")
            db.execute(
                "INSERT INTO static_adapter_designs "
                "(batch_sha256,manifest_json,envelopes_json,state) "
                "VALUES (?,?,?,'DESIGN_ONLY_DISABLED')",
                (manifest["manifest_sha256"], encoded_manifest, encoded_envelopes),
            )
            db.executemany(
                "INSERT INTO static_adapter_request_ids(request_id,batch_sha256) "
                "VALUES (?,?)",
                [(request_id, manifest["manifest_sha256"]) for request_id in ids],
            )
            status = "STAGED_DESIGN_ONLY"
        _audit(db)
    return {
        "schema": SCHEMA, "status": status,
        "batch_sha256": manifest["manifest_sha256"],
        "request_count": manifest["request_count"],
        "execution_authorized": False, "results_verified": False,
        "jobs_created": 0,
    }


def audit_static_adapter_designs(state: DurableResearchState) -> dict:
    """Read-only verification after initial table creation, no worker access."""
    if not isinstance(state, DurableResearchState):
        raise ValueError("Expected durable state store")
    with state._connection() as db:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='static_adapter_designs'"
        ).fetchone()
        if exists is None:
            orphan = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='static_adapter_request_ids'"
            ).fetchone()
            if orphan is not None:
                raise ValueError("Incomplete static design tables; refusing implicit repair")
            return {"schema": SCHEMA, "batches": 0, "requests": 0,
                    "state": "DESIGN_ONLY_DISABLED",
                    "execution_authorized": False, "results_verified": False,
                    "jobs_created": 0}
        return _audit(db)
