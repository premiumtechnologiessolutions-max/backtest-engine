"""Synthetic integration of both independently staged unverified inboxes."""
import hashlib
import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_external_receipts import stage_external_receipt
from scripts.unverified_receipt_inbox import UnverifiedReceiptInbox
from scripts.durable_receipt_inventory import audit_all_external_receipts
from scripts.durable_operations_gate import evaluate
from scripts.research_job_queue import _canonical
from norisk_quant.external_queue_binding import bind_claim
from norisk_quant.external_research_bridge import result_receipt


def fixture(tmp_path):
    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/example.md",
        "frozen_spec_sha256": "1" * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40, "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31", "status": "QUEUED_NOT_EXECUTED",
    }
    record = {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}
    state = DurableResearchState(tmp_path / "state.sqlite3")
    state.ingest_record(record)
    claim = state.claim_next("worker-A", now_ms=1000)
    state.start_reconciliation(
        record["fingerprint"], claim["attempt_id"],
        claim["fencing_token"], claim["worker"], now_ms=1100)
    binding = bind_claim(record, claim, engine="lean",
                         source_sha256="3" * 64, code_sha256="4" * 64)
    data = b'{"synthetic":"unit-test"}'
    digest = hashlib.sha256(data).hexdigest()
    receipt = result_receipt(
        binding["external_request"], provider_build_sha256="6" * 64,
        artifact_sha256=digest, status="completed_unverified")
    return state, record, claim, binding, data, digest, receipt


def test_gate_identifies_both_receipt_formats_and_no_approval(tmp_path):
    state, record, claim, binding, data, digest, receipt = fixture(tmp_path)
    legacy = UnverifiedReceiptInbox(state)
    legacy.stage(record, claim, binding, receipt,
                 actual_artifact_sha256=digest, now_ms=1200)
    stage_external_receipt(
        state, record, claim, binding, receipt,
        artifact_bytes=data, now_ms=1200)
    counts = audit_all_external_receipts(state)
    assert counts["unverified_receipts"] == 2
    assert counts["metadata_only_unverified"] == 1
    assert counts["byte_backed_unverified"] == 1
    assert counts["accepted_results"] == 0
    code, payload = evaluate(state.database, now_ms=1250)
    assert code == 2
    assert payload["receipt_inbox"] == counts
    assert payload["status"] == "OPERATOR_ATTENTION"


def test_metadata_only_still_requires_attention(tmp_path):
    state, record, claim, binding, data, digest, receipt = fixture(tmp_path)
    UnverifiedReceiptInbox(state).stage(
        record, claim, binding, receipt, actual_artifact_sha256=digest,
        now_ms=1200)
    code, payload = evaluate(state.database, now_ms=1250)
    assert code == 2
    assert payload["receipt_inbox"]["metadata_only_unverified"] == 1


def test_tampered_metadata_receipt_fails_health_gate(tmp_path):
    state, record, claim, binding, data, digest, receipt = fixture(tmp_path)
    UnverifiedReceiptInbox(state).stage(
        record, claim, binding, receipt, actual_artifact_sha256=digest,
        now_ms=1200)
    with state._write() as db:
        db.execute(
            "UPDATE unverified_receipts SET fencing_token=99 "
            "WHERE request_id=?", (record["fingerprint"],)
        )
    with pytest.raises(ValueError, match="Disconnected"):
        audit_all_external_receipts(state)
    code, payload = evaluate(state.database, now_ms=1250)
    assert code == 3 and payload["status"] == "INVALID"


def test_gate_idle_empty_inboxes_are_healthy(tmp_path):
    state = DurableResearchState(tmp_path / "state.sqlite3")
    code, payload = evaluate(state.database, now_ms=1000)
    assert code == 0
    assert payload["receipt_inbox"]["unverified_receipts"] == 0
    assert payload["receipt_inbox"]["accepted_results"] == 0
