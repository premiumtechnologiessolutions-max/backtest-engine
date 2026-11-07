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
    assert store.claim_next("worker-B", lease_seconds=10, now_ms=2001) is None
    with pytest.raises(ValueError, match="confirm worker process exit"):
        store.requeue_expired(request_id, now_ms=2001)
    with pytest.raises(ValueError, match="not eligible"):
        store.requeue_expired(request_id, process_exit_confirmed=True, now_ms=1999)
    assert store.requeue_expired(request_id, process_exit_confirmed=True, now_ms=2001)
    b = store.claim_next("worker-B", lease_seconds=10, now_ms=2001)
    assert b["fencing_token"] == a["fencing_token"] + 1
    assert a["attempt_no"] == 1
    assert b["attempt_no"] == 2
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


def test_cancel_request_is_idempotent_and_fenced_acknowledgement(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    claim = store.claim_next("worker-A", lease_seconds=10, now_ms=1000)
    assert store.cancel(ident) == "CANCEL_REQUESTED"
    assert store.cancel(ident) == "CANCEL_REQUESTED"
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        store.acknowledge_cancel(ident, claim["attempt_id"], 0,
                                 "worker-A", now_ms=1500)
    store.acknowledge_cancel(ident, claim["attempt_id"],
                             claim["fencing_token"], "worker-A", now_ms=1500)
    assert store.status(ident)["state"] == "CANCELLED"
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        store.acknowledge_cancel(ident, claim["attempt_id"],
                                 claim["fencing_token"], "worker-A", now_ms=1500)
    assert store.claim_next("worker-B", now_ms=20000) is None
    with store._connection() as db:
        transitions = [row[0] for row in db.execute(
            "SELECT to_state FROM events WHERE request_id=? ORDER BY event_id",
            (ident,))]
    assert transitions == ["QUEUED", "RUNNING", "CANCEL_REQUESTED", "CANCELLED"]


def test_expired_cancel_requires_supervisor_confirmed_exit(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    claim = store.claim_next("worker-A", lease_seconds=1, now_ms=1000)
    assert store.cancel(ident) == "CANCEL_REQUESTED"
    with pytest.raises(ValueError, match="confirm worker process exit"):
        store.finalize_expired_cancel(ident, now_ms=3000)
    with pytest.raises(ValueError, match="not eligible"):
        store.finalize_expired_cancel(
            ident, process_exit_confirmed=True, now_ms=1500)
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        store.acknowledge_cancel(ident, claim["attempt_id"],
                                 claim["fencing_token"], "worker-A", now_ms=3000)
    assert store.finalize_expired_cancel(
        ident, process_exit_confirmed=True, now_ms=3000) is True
    assert store.finalize_expired_cancel(
        ident, process_exit_confirmed=True, now_ms=3000) is False
    assert store.status(ident)["state"] == "CANCELLED"
    assert store.claim_next("worker-B", now_ms=5000) is None


def test_operations_snapshot_distinguishes_expired_lease_from_success(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    empty = store.operational_snapshot(now_ms=1000)
    assert empty["by_state"] == {"QUEUED": 1}
    assert empty["expired_active_or_cancel_leases"] == 0
    assert empty["accepted_results"] == "NOT_IMPLEMENTED"
    claim = store.claim_next("worker-A", lease_seconds=1, now_ms=1000)
    active = store.operational_snapshot(now_ms=1500)
    assert active["by_state"] == {"RUNNING": 1}
    assert active["expired_active_or_cancel_leases"] == 0
    assert not active["requires_operator_attention"]
    stale = store.operational_snapshot(now_ms=2001)
    assert stale["expired_active_or_cancel_leases"] == 1
    assert stale["requires_operator_attention"]
    assert stale["accepted_results"] == "NOT_IMPLEMENTED"
    assert store.cancel(ident) == "CANCEL_REQUESTED"
    pending = store.operational_snapshot(now_ms=2001)
    assert pending["by_state"] == {"CANCEL_REQUESTED": 1}
    assert pending["expired_active_or_cancel_leases"] == 1
    assert pending["broker_order_placement_enabled"] is False
    with pytest.raises(ValueError, match="snapshot clock"):
        store.operational_snapshot(now_ms=True)


def test_expired_reconciling_attempt_cannot_be_reclaimed_without_supervisor(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    a = store.claim_next("worker-A", lease_seconds=1, now_ms=1000)
    store.start_reconciliation(ident, a["attempt_id"], a["fencing_token"],
                               "worker-A", now_ms=1500)
    assert store.claim_next("worker-B", now_ms=2001) is None
    assert store.operational_snapshot(now_ms=2001)["requires_operator_attention"]
    assert store.requeue_expired(ident, process_exit_confirmed=True, now_ms=2001)
    b = store.claim_next("worker-B", now_ms=2001)
    assert b["fencing_token"] == 2
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        store.quarantine(ident, a["attempt_id"], a["fencing_token"],
                         "worker-A", now_ms=2001)


def test_expired_requeue_refuses_cancelled_and_live_leases(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    with pytest.raises(ValueError, match="not eligible"):
        store.requeue_expired(ident, process_exit_confirmed=True, now_ms=1000)
    store.claim_next("worker-A", lease_seconds=10, now_ms=1000)
    with pytest.raises(ValueError, match="not eligible"):
        store.requeue_expired(ident, process_exit_confirmed=True, now_ms=1500)
    store.cancel(ident)
    with pytest.raises(ValueError, match="not eligible"):
        store.requeue_expired(ident, process_exit_confirmed=True, now_ms=20000)


def test_durable_integrity_audit_across_requeue_and_cancellation(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    assert store.audit_integrity()["checked_jobs"] == 1
    first = store.claim_next("worker-A", lease_seconds=1, now_ms=1000)
    store.heartbeat(ident, first["attempt_id"], first["fencing_token"],
                    "worker-A", lease_seconds=1, now_ms=1100)
    assert store.audit_integrity()["checked_jobs"] == 1
    store.requeue_expired(ident, process_exit_confirmed=True, now_ms=2100)
    assert store.audit_integrity()["checked_jobs"] == 1
    second = store.claim_next("worker-B", lease_seconds=10, now_ms=2200)
    store.start_reconciliation(ident, second["attempt_id"],
                               second["fencing_token"], "worker-B", now_ms=2300)
    store.cancel(ident)
    store.acknowledge_cancel(ident, second["attempt_id"],
                             second["fencing_token"], "worker-B", now_ms=2400)
    assert store.audit_integrity()["checked_jobs"] == 1


def test_durable_integrity_audit_rejects_tampered_attempt_and_event(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    store.claim_next("worker-A", lease_seconds=10, now_ms=1000)
    with store._write() as db:
        db.execute("UPDATE attempts SET fencing_token=99 WHERE request_id=?", (ident,))
    with pytest.raises(ValueError, match="attempt sequence"):
        store.audit_integrity()
    with store._write() as db:
        db.execute("UPDATE attempts SET fencing_token=1 WHERE request_id=?", (ident,))
        db.execute("UPDATE events SET from_state='CANCELLED' "
                   "WHERE request_id=? AND to_state='RUNNING'", (ident,))
    with pytest.raises(ValueError, match="event chain"):
        store.audit_integrity()


def test_durable_integrity_audit_rejects_frozen_record_drift(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    with store._write() as db:
        db.execute("UPDATE jobs SET frozen_json='{}' WHERE request_id=?", (ident,))
    with pytest.raises(ValueError, match="Frozen durable research request"):
        store.audit_integrity()


@pytest.mark.parametrize("transition", ["QUEUED", "RUNNING", "RECONCILING"])
def test_integrity_audit_rejects_forged_event_fencing(tmp_path, transition):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    claim = store.claim_next("worker-A", lease_seconds=10, now_ms=1000)
    store.start_reconciliation(ident, claim["attempt_id"],
                               claim["fencing_token"], "worker-A", now_ms=1500)
    assert store.audit_integrity()["checked_jobs"] == 1
    with store._write() as db:
        db.execute("UPDATE events SET fencing_token=99 "
                   "WHERE request_id=? AND to_state=?", (ident, transition))
    with pytest.raises(ValueError, match="event fencing mismatch"):
        store.audit_integrity()


def test_integrity_audit_rejects_missing_claim_transition(tmp_path):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    claim = store.claim_next("worker-A", lease_seconds=10, now_ms=1000)
    store.start_reconciliation(ident, claim["attempt_id"],
                               claim["fencing_token"], "worker-A", now_ms=1500)
    with store._write() as db:
        db.execute("DELETE FROM events WHERE request_id=? "
                   "AND to_state='RUNNING'", (ident,))
    with pytest.raises(ValueError, match="event chain"):
        store.audit_integrity()


@pytest.mark.parametrize("target", ["attempt", "event"])
def test_integrity_audit_rejects_claim_timestamp_drift(tmp_path, target):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    store.claim_next("worker-A", lease_seconds=10, now_ms=1000)
    assert store.audit_integrity()["checked_jobs"] == 1
    with store._write() as db:
        if target == "attempt":
            db.execute("UPDATE attempts SET claimed_ms=claimed_ms+1 "
                       "WHERE request_id=?", (ident,))
        else:
            db.execute("UPDATE events SET created_ms=created_ms+1 "
                       "WHERE request_id=? AND to_state='RUNNING'", (ident,))
    with pytest.raises(ValueError, match="claim/event timestamp mismatch"):
        store.audit_integrity()


@pytest.mark.parametrize("after_requeue", [False, True])
def test_integrity_audit_rejects_stale_queued_attempt_identity(tmp_path, after_requeue):
    store = state.DurableResearchState(tmp_path / "state.sqlite3")
    ident = store.ingest_record(frozen_request())
    if after_requeue:
        first = store.claim_next("worker-A", lease_seconds=1, now_ms=1000)
        store.requeue_expired(ident, process_exit_confirmed=True, now_ms=2001)
        stale_attempt = first["attempt_id"]
    else:
        stale_attempt = "forged-owner"
    assert store.status(ident)["state"] == "QUEUED"
    assert store.audit_integrity()["checked_jobs"] == 1
    with store._write() as db:
        db.execute("UPDATE jobs SET attempt_id=? WHERE request_id=?",
                   (stale_attempt, ident))
    with pytest.raises(ValueError, match="stale attempt identity"):
        store.audit_integrity()
