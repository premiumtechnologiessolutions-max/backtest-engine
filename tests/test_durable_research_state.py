"""Synthetic durable job admission + lease-fencing tests (never real orders)."""
from concurrent.futures import ThreadPoolExecutor
import hashlib

import pytest

from scripts import durable_research_state as state
from scripts.research_job_queue import _canonical, enqueue


def frozen_request(seed="1"):
    body = {
        "schema_version": 1,
        "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028",
        "frozen_spec": "research/frozen-contract.md",
        "frozen_spec_sha256": seed * 64,
        "registry_sha256": "2" * 64,
        "source_commit": "a" * 40,
        "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31",
        "status": "QUEUED_NOT_EXECUTED",
    }
    return {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}


def test_existing_file_queue_intake_is_idempotent(tmp_path):
    request = frozen_request()
    enqueue(tmp_path, request)
    store = state.DurableResearchState(tmp_path / "private" / "state.sqlite3")
    assert store.import_existing_queue(tmp_path) == 1
    assert store.import_existing_queue(tmp_path) == 1
    ident = request["fingerprint"]
    assert store.status(ident)["state"] == "QUEUED"
    assert store.status(ident)["attempt_no"] == 0
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_100_duplicate_ingestions_still_only_one_job(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    request = frozen_request()
    with ThreadPoolExecutor(max_workers=10) as pool:
        assert list(pool.map(store.ingest_record, [request] * 100)) == [
            request["fingerprint"]
        ] * 100
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 1


def test_two_workers_racing_claim_produce_one_owner(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = state.DurableResearchState(path)
    store.ingest_record(frozen_request())
    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = list(pool.map(lambda worker: state.DurableResearchState(
            path).claim_next(worker, lease_seconds=10, now_ms=1000),
            ("worker-A", "worker-B")))
    claims = [answer for answer in answers if answer is not None]
    assert len(claims) == 1
    assert claims[0]["fencing_token"] == 1
    assert store.status(claims[0]["request_id"])["attempt_no"] == 1


def test_expired_worker_cannot_heartbeat_reconcile_or_quarantine(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    request_id = store.ingest_record(frozen_request())
    a = store.claim_next("worker-A", lease_seconds=1, now_ms=1000)
    assert store.claim_next("worker-B", lease_seconds=1, now_ms=1500) is None
    b = store.claim_next("worker-B", lease_seconds=10, now_ms=2001)
    assert b["fencing_token"] == a["fencing_token"] + 1
    assert b["attempt_no"] == a["attempt_no"] if "attempt_no" in a else 2
    assert b["attempt_id"] != a["attempt_id"]
    for action in (
        lambda: store.heartbeat(request_id, a["attempt_id"], a["fencing_token"],
                                "worker-A", now_ms=2001),
        lambda: store.start_reconciliation(request_id, a["attempt_id"],
                                           a["fencing_token"], "worker-A",
                                           now_ms=2001),
        lambda: store.quarantine(request_id, a["attempt_id"], a["fencing_token"],
                                 "worker-A", now_ms=2001),
    ):
        with pytest.raises(ValueError, match="Stale or unauthorized"):
            action()
    store.start_reconciliation(request_id, b["attempt_id"], b["fencing_token"],
                               "worker-B", now_ms=2001)
    assert store.status(request_id)["state"] == "RECONCILING"
    store.quarantine(request_id, b["attempt_id"], b["fencing_token"],
                     "worker-B", now_ms=2002)
    assert store.status(request_id)["state"] == "QUARANTINED"
    assert store.claim_next("worker-C", now_ms=3000) is None


def test_cancellation_prevents_reclaim_and_result_publication(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    id_a = store.ingest_record(frozen_request("1"))
    id_b = store.ingest_record(frozen_request("3"))
    assert store.cancel(id_a) == "CANCELLED"
    assert store.cancel(id_a) == "CANCELLED"
    claim = store.claim_next("worker-A", lease_seconds=30, now_ms=1000)
    assert claim["request_id"] == id_b
    assert store.cancel(id_b) == "CANCEL_REQUESTED"
    assert store.claim_next("worker-B", now_ms=90000) is None
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        store.heartbeat(id_b, claim["attempt_id"], claim["fencing_token"],
                        "worker-A", now_ms=2000)
    assert store.status(id_b)["state"] == "CANCEL_REQUESTED"


def test_invalid_request_and_lease_are_rejected(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    record = frozen_request()
    tampered = dict(record, frozen_spec_sha256="5" * 64)
    with pytest.raises(ValueError, match="Tampered"):
        store.ingest_record(tampered)
    store.ingest_record(record)
    with pytest.raises(ValueError, match="worker"):
        store.claim_next("invalid/worker")
    with pytest.raises(ValueError, match="lease"):
        store.claim_next("good-worker", lease_seconds=0)
    assert store.status(record["fingerprint"])["state"] == "QUEUED"
