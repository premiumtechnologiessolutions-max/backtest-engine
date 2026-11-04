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

from norisk_quant.native_export_parity_pipeline import (
    NativeExport, _build_native_export_parity,
)
from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR
from scripts.durable_cross_engine_parity import stage_unverified_cross_engine_parity
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
    """Stage only full-source hashes; every result stays UNVERIFIED.

    Parity and provenance are written in two fenced transactions. A failed
    source write leaves existing parity quarantined, never accepted.
    """
    if (not isinstance(state, DurableResearchState)
            or type(claim) is not dict
            or type(now_ms) is not int or now_ms < 0):
        raise ValueError("Invalid durable vendor stage request")
    bundle, ledgers = _build_native_export_parity(
        blueprint, native_ledger, vendor_exports)
    report = stage_unverified_cross_engine_parity(
        state, claim, blueprint, ledgers, now_ms=now_ms)
    if report["diagnostic_sha256"] != bundle["parity_diagnostic"]["diagnostic_sha256"]:
        raise ValueError("Stored comparison diverges from vendor export")
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
    if len(payload) > _MAX:
        raise ValueError("Vendor source manifest exceeds bound")
    checksum = _digest(payload)
    with state._write() as db:
        row = state._owned(
            db, claim["request_id"], claim["attempt_id"],
            claim["fencing_token"], claim["worker"], now_ms)
        if row["state"] != "RECONCILING" or row["attempt_no"] != claim["attempt_no"]:
            raise ValueError("Only owned reconciling attempts can stage vendor source")
        _schema(db)
        stored_report = db.execute(
            "SELECT report_sha256 FROM unverified_cross_engine_parity "
            "WHERE attempt_id=? AND request_id=? AND fencing_token=?",
            (claim["attempt_id"], claim["request_id"], claim["fencing_token"]),
        ).fetchone()
        if stored_report is None or stored_report["report_sha256"] != report["report_sha256"]:
            raise ValueError("Unmatched cross-engine comparison identity")
        existing = db.execute(
            "SELECT * FROM unverified_native_export_sources WHERE attempt_id=?",
            (claim["attempt_id"],),
        ).fetchone()
        values = (claim["request_id"], claim["fencing_token"],
                  claim["worker"], report["report_sha256"], checksum, payload)
        if existing:
            if (tuple(existing[k] for k in (
                    "request_id", "fencing_token", "worker", "parity_sha256",
                    "manifest_sha256", "manifest_json")) != values
                    or existing["state"] != "UNVERIFIED"):
                raise ValueError("Immutable native source evidence conflict")
            action = "ALREADY_STAGED_UNVERIFIED"
        else:
            db.execute(
                "INSERT INTO unverified_native_export_sources "
                "(attempt_id,request_id,fencing_token,worker,"
                "parity_sha256,manifest_sha256,manifest_json,state)"
                " VALUES (?,?,?,?,?,?,?,'UNVERIFIED')",
                (claim["attempt_id"], *values),
            )
            action = "STAGED_UNVERIFIED"
    return {
        "schema": SCHEMA, "status": action,
        "attempt_id": claim["attempt_id"], "manifest_sha256": checksum,
        "parity_report_sha256": report["report_sha256"],
        "vendor_exports": len(bundle["provider_exports"]),
        "accepted": False, "execution_authorized": False,
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
