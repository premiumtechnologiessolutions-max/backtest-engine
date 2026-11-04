"""SQLite-fenced real OS synthetic worker fault receipts and recovery."""
import hashlib
import sys

import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.supervised_synthetic_fault_lab import supervised_synthetic_fault_probe
from scripts.durable_supervisor_fault_receipts import (
    stage_supervisor_fault_receipt, audit_supervisor_fault_receipts,
)
from scripts.durable_worker_process_supervisor import (
    LinuxProcInspector, recover_expired_process_after_exit)
from scripts.research_job_queue import _canonical

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux /proc only")


def case(tmp_path):
    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/example.md",
        "frozen_spec_sha256": "1" * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40, "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31", "status": "QUEUED_NOT_EXECUTED",
    }
    record = {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}
    state = DurableResearchState(tmp_path / "control.sqlite3")
    state.ingest_record(record)
    claim = state.claim_next("fault-probe-worker", now_ms=1000, lease_seconds=10)
    return state, claim, record


def test_real_timeout_proof_is_durable_and_idempotent(tmp_path):
    store, claim, record = case(tmp_path)
    output = supervised_synthetic_fault_probe(
        store, claim, now_ms=1200, fault="stall", wall_seconds=1)
    assert output["result"] == "FAILED_WALL_DEADLINE"
    first = stage_supervisor_fault_receipt(
        store, claim, output, now_ms=1400)
    assert first["status"] == "STAGED_SYNTHETIC_UNVERIFIED"
    next_result = stage_supervisor_fault_receipt(
        store, claim, output, now_ms=1401)
    assert next_result["status"] == "ALREADY_STAGED_SYNTHETIC_UNVERIFIED"
    audited = audit_supervisor_fault_receipts(store)
    assert audited["reports"] == 1 and audited["faults"] == 1
    assert audited["accepted"] == 0
    assert store.status(record["fingerprint"])["state"] == "RUNNING"


def test_forged_accepted_or_modified_pid_is_rejected(tmp_path):
    store, claim, record = case(tmp_path)
    output = supervised_synthetic_fault_probe(
        store, claim, now_ms=1200, fault="digest")
    with pytest.raises(ValueError, match="no-execution"):
        stage_supervisor_fault_receipt(
            store, claim, {**output, "research_result_accepted": True}, now_ms=1300)
    with pytest.raises(ValueError, match="OS process identity"):
        stage_supervisor_fault_receipt(
            store, claim, {**output, "pid": output["pid"] + 1}, now_ms=1300)
    assert audit_supervisor_fault_receipts(store)["reports"] == 0


def test_manual_receipt_tampering_poisoned_in_read_only_audit(tmp_path):
    store, claim, record = case(tmp_path)
    output = supervised_synthetic_fault_probe(
        store, claim, now_ms=1200, fault="nonzero")
    stage_supervisor_fault_receipt(store, claim, output, now_ms=1300)
    with store._write() as db:
        db.execute(
            "UPDATE unverified_supervisor_fault_receipts SET report_json='{}'"
            " WHERE attempt_id=?", (claim["attempt_id"],))
    with pytest.raises(ValueError, match="Corrupt"):
        audit_supervisor_fault_receipts(store)


def test_fault_receipt_preserves_os_exit_recovery_fencing(tmp_path):
    store, claim, record = case(tmp_path)
    output = supervised_synthetic_fault_probe(
        store, claim, now_ms=1200, fault="nonzero")
    stage_supervisor_fault_receipt(store, claim, output, now_ms=1300)
    assert recover_expired_process_after_exit(
        store, claim["request_id"], LinuxProcInspector(), now_ms=11001)
    assert audit_supervisor_fault_receipts(store)["faults"] == 1
    assert store.status(record["fingerprint"])["state"] == "QUEUED"
    after = store.claim_next("next-worker", now_ms=11002)
    assert after["fencing_token"] == claim["fencing_token"] + 1


def test_stale_or_outdated_claim_cannot_publish_duplicate_success(tmp_path):
    store, claim, record = case(tmp_path)
    output = supervised_synthetic_fault_probe(
        store, claim, now_ms=1200, fault="digest")
    stale = dict(claim, fencing_token=claim["fencing_token"] + 1)
    with pytest.raises(ValueError, match="Stale"):
        stage_supervisor_fault_receipt(store, stale, output, now_ms=1300)
    with pytest.raises(ValueError, match="Stale"):
        stage_supervisor_fault_receipt(store, claim, output, now_ms=11001)
    assert audit_supervisor_fault_receipts(store)["reports"] == 0


def test_fault_receipt_readonly_health_gate_and_tamper(tmp_path):
    from scripts.durable_operations_gate import evaluate
    store, claim, record = case(tmp_path)
    report = supervised_synthetic_fault_probe(
        store, claim, now_ms=1200, fault="nonzero")
    stage_supervisor_fault_receipt(store, claim, report, now_ms=1300)
    code, healthy_data = evaluate(store.database, now_ms=1300)
    assert code == 2 and healthy_data["status"] == "OPERATOR_ATTENTION"
    assert healthy_data["supervisor_faults"]["reports"] == 1
    assert healthy_data["supervisor_faults"]["faults"] == 1
    assert healthy_data["supervisor_faults"]["accepted"] == 0
    with store._write() as db:
        db.execute(
            "UPDATE unverified_supervisor_fault_receipts "
            "SET report_sha256=? WHERE attempt_id=?",
            ("0" * 64, claim["attempt_id"]))
    broken, failed_data = evaluate(store.database, now_ms=1300)
    assert broken == 3 and failed_data["status"] == "INVALID"
