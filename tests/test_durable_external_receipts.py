"""Fully synthetic SQLite atomic receipt staging, fencing and tamper audit."""
from concurrent.futures import ThreadPoolExecutor
import hashlib

import pytest

from norisk_quant.external_queue_binding import bind_claim
from norisk_quant.external_research_bridge import result_receipt
from scripts.durable_research_state import DurableResearchState
from scripts.durable_external_receipts import (
    audit_staged_external_receipts, read_staged_external_receipt,
    stage_external_receipt,
)
from scripts.durable_operations_gate import evaluate
from scripts.research_job_queue import _canonical


def frozen():
    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/example.md",
        "frozen_spec_sha256": "1" * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40,
        "evaluation_start": "2026-01-01", "evaluation_end": "2026-01-31",
        "status": "QUEUED_NOT_EXECUTED",
    }
    return {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}


def fixture(tmp_path, *, lease_seconds=10):
    store = DurableResearchState(tmp_path / "state.sqlite3")
    record = frozen()
    store.ingest_record(record)
    claim = store.claim_next("worker-A", now_ms=1000,
                             lease_seconds=lease_seconds)
    binding = bind_claim(record, claim, engine="lean",
                         source_sha256="3" * 64, code_sha256="4" * 64)
    artifact = b'{"synthetic":true,"no_market_data":true}'
    receipt = result_receipt(
        binding["external_request"], provider_build_sha256="6" * 64,
        artifact_sha256=hashlib.sha256(artifact).hexdigest(),
        status="completed_unverified")
    return store, record, claim, binding, artifact, receipt


def stage(args, *, now_ms=1200, artifact_bytes=None, receipt=None):
    store, record, claim, binding, artifact, orig_receipt = args
    return stage_external_receipt(
        store, record, claim, binding, receipt or orig_receipt,
        artifact_bytes=artifact if artifact_bytes is None else artifact_bytes,
        now_ms=now_ms)


def reconciling(args):
    store, record, claim, _, _, _ = args
    store.start_reconciliation(
        record["fingerprint"], claim["attempt_id"],
        claim["fencing_token"], claim["worker"], now_ms=1100)


def test_write_only_after_reconciliation_and_never_accepts(tmp_path):
    args = fixture(tmp_path)
    with pytest.raises(ValueError, match="reconciling"):
        stage(args)
    reconciling(args)
    result = stage(args)
    assert result["status"] == "STAGED_UNVERIFIED"
    assert result["accepted"] is False
    assert result["broker_execution_authorized"] is False
    store, record, claim, _, artifact, _ = args
    assert store.status(record["fingerprint"])["state"] == "RECONCILING"
    saved = read_staged_external_receipt(store, claim["attempt_id"])
    assert saved["artifact_bytes"] == artifact
    assert saved["accepted"] is False
    assert audit_staged_external_receipts(store)["unverified_receipts"] == 1


def test_idempotent_repeated_and_parallel_receipt_staging(tmp_path):
    args = fixture(tmp_path)
    reconciling(args)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: stage(args), range(8)))
    assert {r["status"] for r in responses} == {
        "STAGED_UNVERIFIED", "ALREADY_STAGED_UNVERIFIED"}
    store, record, claim, _, _, _ = args
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM external_receipt_inbox").fetchone()[0] == 1


def test_conflicting_artifact_receipt_cannot_overwrite(tmp_path):
    args = fixture(tmp_path)
    reconciling(args)
    stage(args)
    wrong = b"synthetic-mutation"
    with pytest.raises(ValueError, match="not bound"):
        stage(args, artifact_bytes=wrong)
    store, record, claim, binding, _, _ = args
    changed_receipt = result_receipt(
        binding["external_request"], provider_build_sha256="7" * 64,
        artifact_sha256=hashlib.sha256(wrong).hexdigest(),
        status="completed_unverified")
    with pytest.raises(ValueError, match="Immutable external receipt conflict"):
        stage(args, artifact_bytes=wrong, receipt=changed_receipt)
    assert audit_staged_external_receipts(store)["unverified_receipts"] == 1


def test_stale_attempt_after_supervised_requeue_cannot_stage(tmp_path):
    args = fixture(tmp_path, lease_seconds=1)
    reconciling(args)
    store, record, claim, _, _, _ = args
    assert store.requeue_expired(record["fingerprint"],
                                 process_exit_confirmed=True, now_ms=2001)
    second = store.claim_next("worker-B", now_ms=2001)
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        stage(args, now_ms=2001)
    assert second["fencing_token"] == claim["fencing_token"] + 1
    assert audit_staged_external_receipts(store)["unverified_receipts"] == 0


def test_cancelled_or_expired_attempt_cannot_stage(tmp_path):
    args = fixture(tmp_path, lease_seconds=1)
    reconciling(args)
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        stage(args, now_ms=2001)
    store, record, *_ = args
    assert store.cancel(record["fingerprint"]) == "CANCEL_REQUESTED"
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        stage(args, now_ms=1500)


def test_corrupt_stored_blob_fails_gate_closed(tmp_path):
    args = fixture(tmp_path)
    reconciling(args)
    stage(args)
    store, record, claim, _, _, _ = args
    code, payload = evaluate(store.database, now_ms=1250)
    assert code == 2 and payload["receipt_inbox"]["unverified_receipts"] == 1
    with store._write() as db:
        db.execute("UPDATE external_receipt_inbox SET artifact_blob=? "
                   "WHERE attempt_id=?", (b"tampered", claim["attempt_id"]))
    with pytest.raises(ValueError, match="digest drift"):
        audit_staged_external_receipts(store)
    code, payload = evaluate(store.database, now_ms=1250)
    assert code == 3 and payload["status"] == "INVALID"


def test_attempt_history_drift_fails_audit(tmp_path):
    args = fixture(tmp_path)
    reconciling(args)
    stage(args)
    store, record, claim, *_ = args
    with store._write() as db:
        db.execute("UPDATE external_receipt_inbox SET fencing_token=99 "
                   "WHERE attempt_id=?", (claim["attempt_id"],))
    with pytest.raises(ValueError, match="linkage"):
        audit_staged_external_receipts(store)


def test_blob_size_type_and_receipt_approval_rejected(tmp_path):
    args = fixture(tmp_path)
    reconciling(args)
    with pytest.raises(ValueError, match="bounded"):
        stage(args, artifact_bytes=b"x" * 1_048_577)
    with pytest.raises(ValueError, match="bounded"):
        stage(args, artifact_bytes=b"")
    with pytest.raises(ValueError, match="bounded"):
        stage(args, artifact_bytes=bytearray(b"fake"))
    altered = dict(args[-1], accepted=True)
    with pytest.raises(ValueError, match="cannot claim acceptance"):
        stage(args, receipt=altered)


def test_read_after_requeue_remains_historical_not_accepted(tmp_path):
    args = fixture(tmp_path, lease_seconds=1)
    reconciling(args)
    stage(args, now_ms=1200)
    store, record, claim, _, artifact, _ = args
    assert store.requeue_expired(record["fingerprint"],
                                 process_exit_confirmed=True, now_ms=2001)
    saved = read_staged_external_receipt(store, claim["attempt_id"])
    assert saved["artifact_bytes"] == artifact
    assert saved["accepted"] is False
    assert store.status(record["fingerprint"])["state"] == "QUEUED"
