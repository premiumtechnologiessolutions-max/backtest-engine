"""Mirror consistency tests use only synthetic provider receipts, no market runs."""
import hashlib
import json

import pytest

from norisk_quant.external_queue_binding import bind_claim
from norisk_quant.external_research_bridge import result_receipt
from scripts.durable_external_receipts import stage_external_receipt
from scripts.durable_operations_gate import evaluate
from scripts.durable_receipt_inventory import audit_all_external_receipts
from scripts.durable_research_state import DurableResearchState
from scripts.research_job_queue import _canonical
from scripts.unverified_receipt_inbox import UnverifiedReceiptInbox


def _fixture(tmp_path):
    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/example.md",
        "frozen_spec_sha256": "1" * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40, "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31", "status": "QUEUED_NOT_EXECUTED",
    }
    record = {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}
    store = DurableResearchState(tmp_path / "research.sqlite3")
    store.ingest_record(record)
    claim = store.claim_next("worker-A", now_ms=1000)
    store.start_reconciliation(record["fingerprint"], claim["attempt_id"],
                               claim["fencing_token"], claim["worker"], now_ms=1100)
    binding = bind_claim(record, claim, engine="lean",
                         source_sha256="3" * 64, code_sha256="4" * 64)
    data = b'{"synthetic":"unit-test","not-a-backtest":true}'
    digest = hashlib.sha256(data).hexdigest()
    receipt = _receipt(binding, digest, "6")
    return store, record, claim, binding, data, digest, receipt


def _receipt(binding, digest, build):
    return result_receipt(binding["external_request"],
                          provider_build_sha256=build * 64,
                          artifact_sha256=digest,
                          status="completed_unverified")


def _stage_meta(args, receipt=None):
    store, record, claim, binding, data, digest, original = args
    return UnverifiedReceiptInbox(store).stage(
        record, claim, binding, receipt or original,
        actual_artifact_sha256=digest, now_ms=1200)


def _stage_bytes(args, receipt=None):
    store, record, claim, binding, data, digest, original = args
    return stage_external_receipt(
        store, record, claim, binding, receipt or original,
        artifact_bytes=data, now_ms=1200)


def test_same_evidence_can_be_mirrored_as_one_logical_attempt(tmp_path):
    args = _fixture(tmp_path)
    _stage_meta(args)
    _stage_bytes(args)
    count = audit_all_external_receipts(args[0])
    assert count["unverified_receipts"] == 2
    assert count["logical_unverified_attempts"] == 1
    assert count["mirrored_attempts"] == 1
    assert count["accepted_results"] == 0
    code, _ = evaluate(args[0].database, now_ms=1201)
    assert code == 2


@pytest.mark.parametrize("first", ["metadata", "bytes"])
def test_conflicting_valid_provider_receipts_cannot_stage(first, tmp_path):
    args = _fixture(tmp_path)
    alternative = _receipt(args[3], args[5], "7")
    if first == "metadata":
        _stage_meta(args)
        with pytest.raises(ValueError, match="Cross-inbox"):
            _stage_bytes(args, receipt=alternative)
    else:
        _stage_bytes(args)
        with pytest.raises(ValueError, match="Cross-inbox"):
            _stage_meta(args, receipt=alternative)
    assert audit_all_external_receipts(args[0])["unverified_receipts"] == 1


def test_rewritten_legacy_receipt_even_with_new_valid_digests_fails_audit(tmp_path):
    args = _fixture(tmp_path)
    _stage_meta(args)
    _stage_bytes(args)
    store, record, claim, binding, data, digest, receipt = args
    alternate = _receipt(binding, digest, "7")
    with store._write() as db:
        row = db.execute("SELECT payload_json FROM unverified_receipts").fetchone()
        payload = json.loads(row["payload_json"])
        payload["receipt"] = alternate
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True).encode("ascii")
        db.execute("UPDATE unverified_receipts SET payload_json=?, receipt_sha256=?",
                   (encoded.decode("ascii"), hashlib.sha256(encoded).hexdigest()))
    with pytest.raises(ValueError, match="Cross-inbox"):
        audit_all_external_receipts(store)
    code, info = evaluate(store.database, now_ms=1250)
    assert code == 3
    assert info["status"] == "INVALID"


def test_metadata_only_is_not_evidence_of_artifact_bytes(tmp_path):
    args = _fixture(tmp_path)
    _stage_meta(args)
    counts = audit_all_external_receipts(args[0])
    assert counts["metadata_only_unverified"] == 1
    assert counts["byte_backed_unverified"] == 0
    assert counts["logical_unverified_attempts"] == 1
    assert counts["mirrored_attempts"] == 0
    assert counts["accepted_results"] == 0


def test_byte_backed_only_does_not_claim_acceptance(tmp_path):
    args = _fixture(tmp_path)
    _stage_bytes(args)
    counts = audit_all_external_receipts(args[0])
    assert counts["metadata_only_unverified"] == 0
    assert counts["byte_backed_unverified"] == 1
    assert counts["logical_unverified_attempts"] == 1
    assert counts["accepted_results"] == 0
