"""Immutable SQLite registry for planned Quant Engine DAGs. NO EXECUTION.

Binds every frozen sharded campaign to a single transactionally stored
node/dependency graph. This registry never feeds the executable research queue
and cannot claim, complete, or accept a research job.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import zlib

from norisk_quant.campaign_sharding import verify_sharded_campaign
from scripts.durable_research_state import DurableResearchState

SCHEMA = "NRFX_DURABLE_INERT_CAMPAIGN_REGISTRY_V1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_MANIFEST_RAW = 64 * 1024 * 1024
_MAX_NODE_COUNT = 100_000


def _canon(obj: object) -> bytes:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _tables(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS construction_campaigns("
        "campaign_sha TEXT PRIMARY KEY, manifest_compressed BLOB NOT NULL,"
        "manifest_sha256 TEXT NOT NULL, node_count INTEGER NOT NULL,"
        "strategy_count INTEGER NOT NULL, shard_count INTEGER NOT NULL,"
        "state TEXT NOT NULL CHECK(state='DESIGNED_NOT_EXECUTED'))"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS construction_nodes("
        "campaign_sha TEXT NOT NULL REFERENCES construction_campaigns(campaign_sha),"
        "node_id TEXT NOT NULL, shard_index INTEGER NOT NULL,"
        "stage TEXT NOT NULL, depends_json TEXT NOT NULL,"
        "node_json TEXT NOT NULL,"
        "state TEXT NOT NULL CHECK(state='DESIGNED_NOT_EXECUTED'),"
        "PRIMARY KEY(campaign_sha, node_id))"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS construction_nodes_by_shard"
        " ON construction_nodes(campaign_sha, shard_index)"
    )


def _rows(design: dict) -> list[tuple]:
    entries = []
    for shard in design["frozen_shards"]:
        number = shard["shard_index"]
        for node in shard["blueprint"]["dag"]:
            ident = f"{number:04d}/{node['id']}"
            depends = [f"{number:04d}/{dep}" for dep in node["depends_on"]]
            entries.append((
                design["sharded_blueprint_sha256"], ident, number,
                node["stage"], _canon(depends).decode("ascii"),
                _canon(node).decode("ascii"), "DESIGNED_NOT_EXECUTED",
            ))
    if (len(entries) != design["total_designed_nodes"]
            or not 1 <= len(entries) <= _MAX_NODE_COUNT
            or len({row[1] for row in entries}) != len(entries)):
        raise ValueError("Frozen research graph is missing or duplicated")
    return entries


def _compressed(design: dict) -> tuple[bytes, str]:
    raw = _canon(design)
    if not 0 < len(raw) <= _MAX_MANIFEST_RAW:
        raise ValueError("Frozen research manifest exceeds bounded size")
    return zlib.compress(raw, level=6), hashlib.sha256(raw).hexdigest()


def _inflate(source: bytes) -> dict:
    if type(source) is not bytes:
        raise ValueError("Untrusted stored campaign manifest")
    decoder = zlib.decompressobj()
    raw = decoder.decompress(source, _MAX_MANIFEST_RAW + 1)
    if (len(raw) > _MAX_MANIFEST_RAW or decoder.unconsumed_tail
            or not decoder.eof or decoder.unused_data):
        raise ValueError("Overlong or incomplete stored campaign manifest")
    try:
        restored = json.loads(raw)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise ValueError("Malformed stored campaign manifest") from exc
    if type(restored) is not dict or _canon(restored) != raw:
        raise ValueError("Noncanonical stored campaign manifest")
    return restored


def _audit_campaign(db: sqlite3.Connection, sha: str) -> dict:
    row = db.execute(
        "SELECT * FROM construction_campaigns WHERE campaign_sha=?",
        (sha,)
    ).fetchone()
    if row is None:
        raise ValueError("Unknown frozen construction campaign")
    verified = verify_sharded_campaign(_inflate(row["manifest_compressed"]))
    manifest, raw_sha = _compressed(verified)
    if (verified["sharded_blueprint_sha256"] != sha
            or row["manifest_compressed"] != manifest
            or row["manifest_sha256"] != raw_sha
            or row["node_count"] != verified["total_designed_nodes"]
            or row["strategy_count"] != verified["strategy_count"]
            or row["shard_count"] != verified["shard_count"]
            or row["state"] != "DESIGNED_NOT_EXECUTED"):
        raise ValueError("Stored campaign manifest or state has drifted")
    expected = _rows(verified)
    observed = db.execute(
        "SELECT campaign_sha,node_id,shard_index,stage,depends_json,"
        "node_json,state FROM construction_nodes WHERE campaign_sha=?"
        " ORDER BY shard_index,node_id", (sha,)
    ).fetchall()
    if sorted(expected) != sorted(tuple(r) for r in observed):
        raise ValueError("Stored campaign nodes, dependencies or states differ")
    return {
        "schema": SCHEMA, "campaign_sha": sha,
        "strategy_count": verified["strategy_count"],
        "shard_count": verified["shard_count"],
        "node_count": len(expected),
        "state": "DESIGNED_NOT_EXECUTED",
        "worker_started": False, "market_data_accessed": False,
        "research_results_accepted": False,
    }


def register_inert_campaign(store: DurableResearchState, design: dict) -> dict:
    """Commit the ENTIRE design and graph in one SQLite write transaction.

    Re-registration is idempotent if and only if the persisted design and all
    nodes are identical. There are NO run, claim or dispatch transitions.
    """
    if not isinstance(store, DurableResearchState):
        raise ValueError("Expected existing durable control-plane database")
    frozen = verify_sharded_campaign(design)
    blob, digest = _compressed(frozen)
    sha = frozen["sharded_blueprint_sha256"]
    rows = _rows(frozen)
    with store._write() as db:
        _tables(db)
        existing = db.execute(
            "SELECT campaign_sha FROM construction_campaigns WHERE campaign_sha=?",
            (sha,)
        ).fetchone()
        if existing is None:
            db.execute(
                "INSERT INTO construction_campaigns("
                "campaign_sha,manifest_compressed,manifest_sha256,"
                "node_count,strategy_count,shard_count,state)"
                " VALUES(?,?,?,?,?,?,'DESIGNED_NOT_EXECUTED')",
                (sha, blob, digest, len(rows),
                 frozen["strategy_count"], frozen["shard_count"]),
            )
            db.executemany(
                "INSERT INTO construction_nodes("
                "campaign_sha,node_id,shard_index,stage,depends_json,node_json,state)"
                " VALUES(?,?,?,?,?,?,?)", rows)
            status = "REGISTERED_INERT"
        else:
            status = "ALREADY_REGISTERED_IDENTICAL"
        audited = _audit_campaign(db, sha)
    return {**audited, "registration_status": status}


def audit_inert_campaign(store: DurableResearchState, sha: str) -> dict:
    if (not isinstance(store, DurableResearchState)
            or type(sha) is not str or not _SHA.fullmatch(sha)):
        raise ValueError("Invalid durable campaign audit request")
    with store._connection() as db:
        return _audit_campaign(db, sha)


def audit_inert_registry(store: DurableResearchState) -> dict:
    """Audit ALL inert campaigns; no false completion from a partial sample."""
    with store._connection() as db:
        table = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table'"
            " AND name='construction_campaigns'"
        ).fetchone()
        if table is None:
            return {"schema": SCHEMA, "campaign_count": 0,
                    "planned_nodes": 0, "execution_enabled": False}
        ids = [row[0] for row in db.execute(
            "SELECT campaign_sha FROM construction_campaigns ORDER BY campaign_sha"
        )]
        reports = [_audit_campaign(db, ident) for ident in ids]
        dangling = db.execute(
            "SELECT COUNT(*) FROM construction_nodes "
            "WHERE campaign_sha NOT IN (SELECT campaign_sha FROM construction_campaigns)"
        ).fetchone()[0]
        if dangling:
            raise ValueError("Orphan inert campaign node")
    return {"schema": SCHEMA, "campaign_count": len(reports),
            "planned_nodes": sum(r["node_count"] for r in reports),
            "execution_enabled": False}
