"""Synthetic-only immutable receipt staging tests; no market execution."""
import hashlib
import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.research_job_queue import _canonical
from scripts.unverified_receipt_inbox import UnverifiedReceiptInbox
from norisk_quant.external_queue_binding import bind_claim
from norisk_quant.external_research_bridge import result_receipt


def setup(tmp_path):
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
    binding = bind_claim(record, claim, engine="lean",
                         source_sha256="3" * 64, code_sha256="4" * 64)
    receipt = result_receipt(binding["external_request"],
                             provider_build_sha256="6" * 64,
                             artifact_sha256="5" * 64,
                             status="completed_unverified")
    return record, state, claim, binding, receipt


def stage(inbox, record, claim, binding, receipt, now=1001):
    return inbox.stage(record, claim, binding, receipt,
                       actual_artifact_sha256="5" * 64, now_ms=now)


def test_stages_only_during_reconciliation_and_idempotent(tmp_path):
    record, state, claim, binding, receipt = setup(tmp_path)
    inbox = UnverifiedReceiptInbox(state)
    with pytest.raises(ValueError, match="RECONCILING"):
        stage(inbox, record, claim, binding, receipt)
    state.start_reconciliation(record["fingerprint"], claim["attempt_id"],
                               claim["fencing_token"], claim["worker"], now_ms=1000)
    first = stage(inbox, record, claim, binding, receipt)
    assert first == stage(inbox, record, claim, binding, receipt)
    assert first["accepted"] is False
    assert inbox.inspect(record["fingerprint"], claim["attempt_id"])["accepted"] is False
    assert state.status(record["fingerprint"])["state"] == "RECONCILING"
    assert state.operational_snapshot(now_ms=1001)["accepted_results"] == "NOT_IMPLEMENTED"


def test_mutated_receipt_and_expired_claim_rejected(tmp_path):
    record, state, claim, binding, receipt = setup(tmp_path)
    inbox = UnverifiedReceiptInbox(state)
    state.start_reconciliation(record["fingerprint"], claim["attempt_id"],
                               claim["fencing_token"], claim["worker"], now_ms=1000)
    stage(inbox, record, claim, binding, receipt)
    with pytest.raises(ValueError):
        stage(inbox, record, claim, binding,
              {**receipt, "accepted": True})
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        stage(inbox, record, claim, binding, receipt, now=121001)


def test_cancelled_claim_and_stored_tampering_fail_closed(tmp_path):
    record, state, claim, binding, receipt = setup(tmp_path)
    inbox = UnverifiedReceiptInbox(state)
    state.start_reconciliation(record["fingerprint"], claim["attempt_id"],
                               claim["fencing_token"], claim["worker"], now_ms=1000)
    stage(inbox, record, claim, binding, receipt)
    with state._write() as db:
        db.execute("UPDATE unverified_receipts SET payload_json='{}' "
                   "WHERE request_id=?", (record["fingerprint"],))
    with pytest.raises(ValueError, match="digest mismatch"):
        inbox.inspect(record["fingerprint"], claim["attempt_id"])
    state.cancel(record["fingerprint"])
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        stage(inbox, record, claim, binding, receipt)
