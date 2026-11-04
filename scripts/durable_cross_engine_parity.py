"""Durable UNVERIFIED cross-engine parity evidence for frozen attempts.

Atomic SQLite staging of reproducible SOURCE-SHAPED diagnostic metadata
only. Never stores raw trade prices, never runs an upstream engine or
promotes a result to accepted. Read-only audit detects later drift.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time

from norisk_quant.campaign_blueprint import verify_blueprint
from norisk_quant.cross_engine_parity import compare_frozen_engine_ledgers
from scripts.durable_research_state import DurableResearchState

SCHEMA = "NRFX_DURABLE_UNVERIFIED_PARITY_INBOX_V1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_REPORT_BYTES = 256 * 1024


def _canonical(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _sha(raw: str) -> str:
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def _clock(value: int | None) -> int:
    now = time.time_ns() // 1_000_000 if value is None else value
    if type(now) is not int or now < 0:
        raise ValueError("Invalid frozen parity audit clock")
    return now


def _table(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS unverified_cross_engine_parity("
        "attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id),"
        "request_id TEXT NOT NULL REFERENCES jobs(request_id),"
        "fencing_token INTEGER NOT NULL, worker TEXT NOT NULL,"
        "blueprint_sha256 TEXT NOT NULL, report_sha256 TEXT NOT NULL,"
        "report_json TEXT NOT NULL, staged_ms INTEGER NOT NULL,"
        "state TEXT NOT NULL CHECK(state='UNVERIFIED_ONLY'))"
    )


def stage_unverified_cross_engine_parity(
    store: DurableResearchState, claim: dict,
    frozen_blueprint: dict, ledgers: dict, *,
    now_ms: int | None = None,
) -> dict:
    """Stage the actual computed diagnostic only for a current fenced attempt.

    Match source commit and UTC window to original durable queue intent.
    The report is recomputed from all canonical ledger rows and is
    captured under one SQLite transaction, but STILL not accepted evidence.
    """
    if not isinstance(store, DurableResearchState) or type(claim) is not dict:
        raise ValueError("Durable parity requires a trusted claim")
    blueprint = verify_blueprint(frozen_blueprint)
    request = claim.get("frozen_request")
    shared = blueprint["normalized_spec"]
    if (type(request) is not dict
            or request.get("source_commit") != shared["source_commit"]
            or request.get("evaluation_start") != shared["evaluation"]["start"]
            or request.get("evaluation_end") != shared["evaluation"]["end"]
            or request.get("fingerprint") != claim.get("request_id")):
        raise ValueError("Frozen parity campaign does not match the durable request")
    report = compare_frozen_engine_ledgers(blueprint, ledgers)
    payload = _canonical(report)
    if len(payload.encode("ascii")) > _MAX_REPORT_BYTES:
        raise ValueError("Bounded cross-engine diagnostic exceeded")
    digest = _sha(payload)
    now = _clock(now_ms)
    with store._write() as db:
        current = store._owned(
            db, claim["request_id"], claim["attempt_id"],
            claim["fencing_token"], claim["worker"], now)
        if (current["state"] != "RECONCILING"
                or current["attempt_no"] != claim["attempt_no"]
                or current["frozen_json"] != _canonical(request)):
            raise ValueError("Only exact reconciling frozen attempt may stage parity")
        _table(db)
        previous = db.execute(
            "SELECT * FROM unverified_cross_engine_parity WHERE attempt_id=?",
            (claim["attempt_id"],)
        ).fetchone()
        identity = (
            claim["request_id"], claim["fencing_token"], claim["worker"],
            blueprint["blueprint_sha256"], digest, payload,
        )
        if previous is not None:
            actual = tuple(previous[key] for key in (
                "request_id", "fencing_token", "worker", "blueprint_sha256",
                "report_sha256", "report_json",
            ))
            if actual != identity or previous["state"] != "UNVERIFIED_ONLY":
                raise ValueError("Immutable parity receipt conflict")
            status = "ALREADY_STAGED_UNVERIFIED"
        else:
            db.execute(
                "INSERT INTO unverified_cross_engine_parity("
                "attempt_id,request_id,fencing_token,worker,blueprint_sha256,"
                "report_sha256,report_json,staged_ms,state)"
                " VALUES(?,?,?,?,?,?,?,?, 'UNVERIFIED_ONLY')",
                (claim["attempt_id"], *identity, now),
            )
            status = "STAGED_UNVERIFIED"
    return {
        "schema": SCHEMA,
        "request_id": claim["request_id"],
        "attempt_id": claim["attempt_id"],
        "blueprint_sha256": blueprint["blueprint_sha256"],
        "report_sha256": digest,
        "diagnostic_sha256": report["diagnostic_sha256"],
        "status": status,
        "field_discrepancy_count": report["field_discrepancy_count"],
        "accepted": False,
        "research_executed_by_staging": False,
        "market_data_accessed_by_staging": False,
    }


def audit_unverified_cross_engine_parity(store: DurableResearchState) -> dict:
    """Read all rows, cross-check attempts, canonical bytes and report digests."""
    if not isinstance(store, DurableResearchState):
        raise ValueError("Expected durable parity store")
    with store._connection() as db:
        has = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table'"
            " AND name='unverified_cross_engine_parity'"
        ).fetchone()
        if has is None:
            return {"schema": SCHEMA, "reports": 0,
                    "discrepancy_fields": 0, "accepted": 0}
        records = db.execute(
            "SELECT r.*,a.request_id AS original_request_id,"
            "a.fencing_token AS original_token,a.worker AS original_worker "
            "FROM unverified_cross_engine_parity r "
            "LEFT JOIN attempts a ON a.attempt_id=r.attempt_id"
        ).fetchall()
        disagreements = 0
        for row in records:
            if (row["original_request_id"] != row["request_id"]
                    or row["original_token"] != row["fencing_token"]
                    or row["original_worker"] != row["worker"]
                    or row["state"] != "UNVERIFIED_ONLY"
                    or type(row["report_json"]) is not str
                    or not 0 < len(row["report_json"]) <= _MAX_REPORT_BYTES
                    or type(row["report_sha256"]) is not str
                    or not _SHA.fullmatch(row["report_sha256"])
                    or _sha(row["report_json"]) != row["report_sha256"]):
                raise ValueError("Disconnected or tampered cross-engine report")
            try:
                report = json.loads(row["report_json"])
                if type(report) is not dict or _canonical(report) != row["report_json"]:
                    raise ValueError("Noncanonical stored parity report")
                intrinsic = report.pop("diagnostic_sha256")
                if intrinsic != _sha(_canonical(report)):
                    raise ValueError("Tampered cross-engine diagnostic")
                report["diagnostic_sha256"] = intrinsic
            except (ValueError, KeyError, TypeError, UnicodeError) as exc:
                raise ValueError("Invalid frozen cross-engine report") from exc
            if (report.get("schema") != "NRFX_CROSS_ENGINE_LEDGER_PARITY_V1"
                    or report.get("blueprint_sha256") != row["blueprint_sha256"]
                    or report.get("strategy_research_accepted") is not False
                    or report.get("upstream_engine_execution_attested") is not False
                    or report.get("market_data_opened") is not False
                    or type(report.get("field_discrepancy_count")) is not int
                    or report["field_discrepancy_count"] < 0):
                raise ValueError("Parity report falsely claims research acceptance")
            disagreements += report["field_discrepancy_count"]
    return {
        "schema": SCHEMA,
        "reports": len(records),
        "discrepancy_fields": disagreements,
        "accepted": 0,
        "raw_trade_ledgers_independently_reattested": False,
    }
