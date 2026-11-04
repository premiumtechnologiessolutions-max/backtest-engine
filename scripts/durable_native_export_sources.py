"""Fenced, unverified native-export source receipt for the Quant Engine.

Connects source-shaped LEAN/Nautilus export bytes to durable row-level parity.
Neither SHA256 nor identical vendor reports prove that a vendor was executed.
No market data are read or external process started.
"""
from __future__ import annotations

import hashlib
import json
import re

import pandas as pd

from norisk_quant.campaign_blueprint import verify_blueprint
from norisk_quant.native_export_parity_pipeline import (
    NativeExport, _build_native_export_parity,
)
from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR
from scripts.durable_cross_engine_parity import (
    _table as _parity_table, _MAX_REPORT_BYTES,
)
from scripts.durable_research_state import DurableResearchState

SCHEMA = "NRFX_NATIVE_SOURCE_INBOX_V1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_MAX = 64 * 1024


def _canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _schema(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS unverified_native_export_sources("
        "attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id),"
        "request_id TEXT NOT NULL REFERENCES jobs(request_id),"
        "fencing_token INTEGER NOT NULL, worker TEXT NOT NULL,"
        "parity_sha256 TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,"
        "manifest_json TEXT NOT NULL,"
        "state TEXT NOT NULL CHECK(state='UNVERIFIED'))"
    )


def stage_native_source_evidence(
    state: DurableResearchState, claim: dict, blueprint: dict,
    native_ledger: pd.DataFrame, vendor_exports: dict[str, NativeExport], *,
    now_ms: int,
) -> dict:
    """Atomically stage parity + native source identities; NEVER accept.

    Both reports are computed and fully size-checked before acquiring
    SQLite's write lock. A single BEGIN IMMEDIATE transaction then checks
    frozen lease, exact request/blueprint identity, both existing receipt
    identities, and either commits BOTH records or rolls back everything.

    Incomplete pre-existing parity-only records are refused for manual
    review: this API does not silently associate a separate earlier write
    with newly submitted vendor bytes. The original parity-only staging API
    remains available for engineering-only comparator diagnostics.
    """
    if (not isinstance(state, DurableResearchState)
            or type(claim) is not dict
            or type(now_ms) is not int or now_ms < 0):
        raise ValueError("Invalid durable vendor stage request")
    frozen = verify_blueprint(blueprint)
    bundle, _ = _build_native_export_parity(
        frozen, native_ledger, vendor_exports)
    report = bundle["parity_diagnostic"]
    comparison_payload = _canonical(report)
    if not 0 < len(comparison_payload) <= _MAX_REPORT_BYTES:
        raise ValueError("Bounded cross-engine diagnostic exceeded")
    comparison_sha = _digest(comparison_payload)
    request = claim.get("frozen_request")
    spec = frozen["normalized_spec"]
    if (type(request) is not dict
            or request.get("source_commit") != spec["source_commit"]
            or request.get("evaluation_start") != spec["evaluation"]["start"]
            or request.get("evaluation_end") != spec["evaluation"]["end"]
            or request.get("fingerprint") != claim.get("request_id")):
        raise ValueError("Frozen parity campaign does not match durable request")
    manifest = {
        "schema": SCHEMA, "blueprint_sha256": bundle["blueprint_sha256"],
        "pipeline_sha256": bundle["pipeline_sha256"],
        "parity_diagnostic_sha256": report["diagnostic_sha256"],
        "vendors": bundle["provider_exports"],
        "vendor_execution_attested": False,
        "sidecar_freeze_attested": False,
        "research_result_accepted": False,
        "state": "UNVERIFIED",
    }
    payload = _canonical(manifest)
    if not 0 < len(payload) <= _MAX:
        raise ValueError("Vendor source manifest exceeds bound")
    checksum = _digest(payload)
    with state._write() as db:
        row = state._owned(
            db, claim["request_id"], claim["attempt_id"],
            claim["fencing_token"], claim["worker"], now_ms)
        if (row["state"] != "RECONCILING"
                or row["attempt_no"] != claim["attempt_no"]
                or row["frozen_json"] != _canonical(request)):
            raise ValueError("Only exact reconciling frozen attempts can stage vendor source")
        _parity_table(db)
        _schema(db)

        parity_identity = (
            claim["request_id"], claim["fencing_token"], claim["worker"],
            frozen["blueprint_sha256"], comparison_sha, comparison_payload,
        )
        source_identity = (
            claim["request_id"], claim["fencing_token"],
            claim["worker"], comparison_sha, checksum, payload,
        )
        current_parity = db.execute(
            "SELECT * FROM unverified_cross_engine_parity WHERE attempt_id=?",
            (claim["attempt_id"],),
        ).fetchone()
        current_source = db.execute(
            "SELECT * FROM unverified_native_export_sources WHERE attempt_id=?",
            (claim["attempt_id"],),
        ).fetchone()

        if (current_parity is None) != (current_source is None):
            raise ValueError(
                "Incomplete existing parity/source evidence; manual review required")
        if current_parity is None:
            db.execute(
                "INSERT INTO unverified_cross_engine_parity("
                "attempt_id,request_id,fencing_token,worker,blueprint_sha256,"
                "report_sha256,report_json,staged_ms,state)"
                " VALUES(?,?,?,?,?,?,?,?, 'UNVERIFIED_ONLY')",
                (claim["attempt_id"], *parity_identity, now_ms),
            )
            db.execute(
                "INSERT INTO unverified_native_export_sources("
                "attempt_id,request_id,fencing_token,worker,"
                "parity_sha256,manifest_sha256,manifest_json,state)"
                " VALUES (?,?,?,?,?,?,?,'UNVERIFIED')",
                (claim["attempt_id"], *source_identity),
            )
            action = "STAGED_UNVERIFIED"
        else:
            stored_parity = tuple(current_parity[k] for k in (
                "request_id", "fencing_token", "worker",
                "blueprint_sha256", "report_sha256", "report_json"))
            stored_source = tuple(current_source[k] for k in (
                "request_id", "fencing_token", "worker",
                "parity_sha256", "manifest_sha256", "manifest_json"))
            if (stored_parity != parity_identity
                    or current_parity["state"] != "UNVERIFIED_ONLY"
                    or stored_source != source_identity
                    or current_source["state"] != "UNVERIFIED"):
                raise ValueError("Immutable atomic native/parity evidence conflict")
            action = "ALREADY_STAGED_UNVERIFIED"
    return {
        "schema": SCHEMA, "status": action,
        "attempt_id": claim["attempt_id"], "manifest_sha256": checksum,
        "parity_report_sha256": comparison_sha,
        "vendor_exports": len(bundle["provider_exports"]),
        "accepted": False, "execution_authorized": False,
        "atomic_two_receipt_commit": True,
        "vendor_runtime_attested": False,
    }

def audit_native_source_evidence(state: DurableResearchState) -> dict:
    """Read-only audit of all source manifests and their parity attempts."""
    with state._connection() as db:
        has = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='unverified_native_export_sources'"
        ).fetchone()
        if not has:
            return {"schema": SCHEMA, "reports": 0,
                    "vendor_exports": 0, "accepted": 0}
        rows = db.execute(
            "SELECT s.*,a.request_id AS a_request,"
            "a.fencing_token AS a_token,a.worker AS a_worker,"
            "p.report_sha256 AS p_sha,p.report_json AS p_json "
            "FROM unverified_native_export_sources s "
            "LEFT JOIN attempts a ON a.attempt_id=s.attempt_id "
            "LEFT JOIN unverified_cross_engine_parity p "
            "ON p.attempt_id=s.attempt_id"
        ).fetchall()
        exports = 0
        for row in rows:
            if (row["state"] != "UNVERIFIED"
                    or row["request_id"] != row["a_request"]
                    or row["fencing_token"] != row["a_token"]
                    or row["worker"] != row["a_worker"]
                    or row["parity_sha256"] != row["p_sha"]
                    or type(row["manifest_json"]) is not str
                    or not 0 < len(row["manifest_json"]) <= _MAX
                    or type(row["manifest_sha256"]) is not str
                    or not _HEX.fullmatch(row["manifest_sha256"])
                    or _digest(row["manifest_json"]) != row["manifest_sha256"]):
                raise ValueError("Altered or orphaned native source manifest")
            try:
                payload = json.loads(row["manifest_json"])
                parity = json.loads(row["p_json"])
            except (TypeError, ValueError) as exc:
                raise ValueError("Malformed native source evidence") from exc
            if (type(payload) is not dict
                    or set(payload) != {
                        "schema", "blueprint_sha256", "pipeline_sha256",
                        "parity_diagnostic_sha256", "vendors",
                        "vendor_execution_attested", "sidecar_freeze_attested",
                        "research_result_accepted", "state"}
                    or payload["schema"] != SCHEMA
                    or payload["state"] != "UNVERIFIED"
                    or payload["vendor_execution_attested"] is not False
                    or payload["sidecar_freeze_attested"] is not False
                    or payload["research_result_accepted"] is not False
                    or payload["parity_diagnostic_sha256"] != parity["diagnostic_sha256"]
                    or payload["blueprint_sha256"] != parity["blueprint_sha256"]
                    or type(payload["vendors"]) is not dict
                    or not payload["vendors"]
                    or _canonical(payload) != row["manifest_json"]):
                raise ValueError("Inconsistent native source manifest")
            for engine, entry in payload["vendors"].items():
                if (engine not in PINNED_VENDOR
                        or type(entry) is not dict
                        or entry.get("engine") != engine
                        or entry.get("pinned_vendor_commit") != PINNED_VENDOR[engine]
                        or entry.get("vendor_execution_attested") is not False
                        or entry.get("status") != "NORMALIZED_NOT_ENGINE_ATTESTED"
                        or entry.get("normalized_ledger_sha256")
                        != parity["normalized_ledger_sha256"].get(engine)):
                    raise ValueError("Source engine pin or ledger binding drift")
                for key in ("raw_source_bytes_sha256",
                            "source_sidecar_bytes_sha256",
                            "source_sidecar_canonical_sha256",
                            "normalized_ledger_sha256"):
                    if type(entry.get(key)) is not str or not _HEX.fullmatch(entry[key]):
                        raise ValueError("Invalid native source checksum")
                exports += 1
    return {"schema": SCHEMA, "reports": len(rows),
            "vendor_exports": exports, "accepted": 0,
            "externally_authenticated": False}
