"""Immutable SQLite receipt for real synthetic supervisor failure-mode probes.

Stores no stdout/stderr contents, only fixed bounded evidence metadata and
SHA256. Every report is always UNVERIFIED and never authorizes research,
automatic requeue, market-data use or any external vendor launch.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from scripts.durable_research_state import DurableResearchState

SCHEMA = "NRFX_DURABLE_SUPERVISOR_FAULT_RECEIPT_V1"
_REPORT_SCHEMA = "NRFX_SYNTHETIC_BOUNDED_WORKER_FAULT_PROOF_V1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_MAX_REPORT = 8192
_REPORT_FIELDS = frozenset({
    "schema", "request_id", "attempt_id", "fencing_token", "boot_id",
    "pid", "start_ticks", "fault_scenario", "result", "exit_code",
    "stdout_sha256", "stderr_sha256", "stdout_bytes", "stderr_bytes",
    "process_group_exit_proven", "worker_claim_state_unchanged",
    "vendor_engine_executed", "market_data_accessed",
    "research_result_accepted", "automatic_retry_triggered",
    "sandbox_for_untrusted_code_proven",
})
_EXPECTED = {
    "digest": "SYNTHETIC_SUCCESS_ONLY",
    "nonzero": "FAILED_NONZERO_EXIT",
    "stderr": "FAILED_NONZERO_EXIT",
    "flood": "FAILED_OUTPUT_BOUND",
    "stall": "FAILED_WALL_DEADLINE",
}


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _digest(data: str) -> str:
    return hashlib.sha256(data.encode("ascii")).hexdigest()


def _verify_report(report: dict) -> str:
    if type(report) is not dict or set(report) != _REPORT_FIELDS:
        raise ValueError("Unexpected synthetic OS supervisor evidence schema")
    if (report["schema"] != _REPORT_SCHEMA
            or report["fault_scenario"] not in _EXPECTED
            or report["result"] != _EXPECTED[report["fault_scenario"]]
            or any(report[k] is not False for k in (
                "vendor_engine_executed", "market_data_accessed",
                "research_result_accepted", "automatic_retry_triggered",
                "sandbox_for_untrusted_code_proven"))
            or any(report[k] is not True for k in (
                "process_group_exit_proven", "worker_claim_state_unchanged"))
            or any(type(report[k]) is not int or report[k] < 0 for k in (
                "pid", "start_ticks", "fencing_token",
                "stdout_bytes", "stderr_bytes"))
            or report["pid"] <= 1 or report["start_ticks"] < 1
            or report["stdout_bytes"] > 1024 or report["stderr_bytes"] > 1024
            or type(report["exit_code"]) is not int
            or any(type(report[k]) is not str or not _HEX.fullmatch(report[k])
                   for k in ("stdout_sha256", "stderr_sha256"))
            or any(type(report[k]) is not str or not report[k]
                   for k in ("request_id", "attempt_id", "boot_id"))):
        raise ValueError("Synthetic OS supervisor receipt violates no-execution policy")
    if report["fault_scenario"] == "digest":
        if (report["exit_code"] != 0
                or report["stderr_bytes"] != 0
                or report["stdout_bytes"] <= 0):
            raise ValueError("Synthetic success requires clean child exit")
    elif report["fault_scenario"] in ("nonzero", "stderr"):
        expected_exit = 19 if report["fault_scenario"] == "nonzero" else 3
        if report["exit_code"] != expected_exit:
            raise ValueError("Synthetic nonzero child exit identity drift")
    else:
        if report["exit_code"] == 0:
            raise ValueError("Synthetic deadline/overflow failure cannot exit successfully")
    encoded = _canonical(report)
    if len(encoded) > _MAX_REPORT:
        raise ValueError("Oversized synthetic supervisor receipt")
    return encoded


def _table(db: sqlite3.Connection) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS unverified_supervisor_fault_receipts("
        "attempt_id TEXT PRIMARY KEY REFERENCES attempts(attempt_id),"
        "request_id TEXT NOT NULL REFERENCES jobs(request_id),"
        "fencing_token INTEGER NOT NULL, worker TEXT NOT NULL,"
        "report_sha256 TEXT NOT NULL, report_json TEXT NOT NULL,"
        "state TEXT NOT NULL CHECK(state='UNVERIFIED_SYNTHETIC_ONLY'))"
    )


def stage_supervisor_fault_receipt(
    store: DurableResearchState, claim: dict, report: dict, *,
    now_ms: int,
) -> dict:
    if (not isinstance(store, DurableResearchState) or type(claim) is not dict
            or type(now_ms) is not int or now_ms < 0):
        raise ValueError("Invalid synthetic supervisor durable stage request")
    encoded = _verify_report(report)
    if (report["request_id"] != claim.get("request_id")
            or report["attempt_id"] != claim.get("attempt_id")
            or report["fencing_token"] != claim.get("fencing_token")):
        raise ValueError("Synthetic evidence does not match its fenced claim")
    digest = _digest(encoded)
    with store._write() as db:
        owner = store._owned(
            db, claim["request_id"], claim["attempt_id"],
            claim["fencing_token"], claim["worker"], now_ms)
        if owner["state"] != "RUNNING" or owner["attempt_no"] != claim["attempt_no"]:
            raise ValueError("Staging requires live RUNNING synthetic worker lease")
        row = db.execute(
            "SELECT * FROM supervisor_process_identity WHERE attempt_id=?",
            (claim["attempt_id"],),
        ).fetchone()
        if (row is None or row["request_id"] != claim["request_id"]
                or row["fencing_token"] != claim["fencing_token"]
                or row["worker"] != claim["worker"]
                or row["boot_id"] != report["boot_id"]
                or row["pid"] != report["pid"]
                or row["start_ticks"] != report["start_ticks"]
                or row["process_group"] != report["pid"]):
            raise ValueError("Synthetic report not tied to durable OS process identity")
        _table(db)
        previous = db.execute(
            "SELECT * FROM unverified_supervisor_fault_receipts"
            " WHERE attempt_id=?", (claim["attempt_id"],),
        ).fetchone()
        values = (claim["request_id"], claim["fencing_token"],
                  claim["worker"], digest, encoded)
        if previous is None:
            db.execute(
                "INSERT INTO unverified_supervisor_fault_receipts "
                "(attempt_id,request_id,fencing_token,worker,report_sha256,"
                "report_json,state) VALUES(?,?,?,?,?,?,'UNVERIFIED_SYNTHETIC_ONLY')",
                (claim["attempt_id"], *values),
            )
            status = "STAGED_SYNTHETIC_UNVERIFIED"
        else:
            original = tuple(previous[k] for k in (
                "request_id", "fencing_token", "worker",
                "report_sha256", "report_json"))
            if (original != values
                    or previous["state"] != "UNVERIFIED_SYNTHETIC_ONLY"):
                raise ValueError("Immutable synthetic supervisor receipt conflict")
            status = "ALREADY_STAGED_SYNTHETIC_UNVERIFIED"
    return {
        "schema": SCHEMA, "attempt_id": claim["attempt_id"],
        "status": status, "report_sha256": digest,
        "failure_type": report["result"],
        "accepted": False, "automatic_retry": False,
    }


def audit_supervisor_fault_receipts(store: DurableResearchState) -> dict:
    """Revalidate all receipts and match the immutable OS process identities."""
    if not isinstance(store, DurableResearchState):
        raise ValueError("Expected existing durable control plane")
    with store._connection() as db:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table'"
            " AND name='unverified_supervisor_fault_receipts'"
        ).fetchone()
        if not exists:
            return {"schema": SCHEMA, "reports": 0,
                    "faults": 0, "accepted": 0}
        rows = db.execute(
            "SELECT r.*,a.request_id AS a_request,"
            "a.fencing_token AS a_token,a.worker AS a_worker,"
            "p.boot_id AS p_boot,p.pid AS p_pid,"
            "p.start_ticks AS p_ticks,p.process_group AS p_group,"
            "p.request_id AS p_request,p.fencing_token AS p_token,"
            "p.worker AS p_worker "
            "FROM unverified_supervisor_fault_receipts r "
            "LEFT JOIN attempts a ON a.attempt_id=r.attempt_id "
            "LEFT JOIN supervisor_process_identity p ON p.attempt_id=r.attempt_id"
        ).fetchall()
        failed = 0
        for row in rows:
            if (row["state"] != "UNVERIFIED_SYNTHETIC_ONLY"
                    or row["a_request"] != row["request_id"]
                    or row["a_token"] != row["fencing_token"]
                    or row["a_worker"] != row["worker"]
                    or row["p_request"] != row["request_id"]
                    or row["p_token"] != row["fencing_token"]
                    or row["p_worker"] != row["worker"]
                    or type(row["report_json"]) is not str
                    or not 0 < len(row["report_json"]) <= _MAX_REPORT
                    or type(row["report_sha256"]) is not str
                    or not _HEX.fullmatch(row["report_sha256"])
                    or _digest(row["report_json"]) != row["report_sha256"]):
                raise ValueError("Corrupt or orphaned synthetic supervisor receipt")
            try:
                report = json.loads(row["report_json"])
            except (TypeError, ValueError, UnicodeError) as exc:
                raise ValueError("Malformed synthetic supervisor receipt JSON") from exc
            if (_verify_report(report) != row["report_json"]
                    or report["attempt_id"] != row["attempt_id"]
                    or report["request_id"] != row["request_id"]
                    or report["fencing_token"] != row["fencing_token"]
                    or report["boot_id"] != row["p_boot"]
                    or report["pid"] != row["p_pid"]
                    or report["pid"] != row["p_group"]
                    or report["start_ticks"] != row["p_ticks"]):
                raise ValueError("Synthetic supervisor evidence no longer matches process")
            if report["result"] != "SYNTHETIC_SUCCESS_ONLY":
                failed += 1
    return {"schema": SCHEMA, "reports": len(rows),
            "faults": failed, "accepted": 0,
            "real_external_engine_attested": False}
