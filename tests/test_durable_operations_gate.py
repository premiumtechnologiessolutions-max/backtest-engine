"""Read-only watchdog gate regression tests; no market data or worker processes."""
import sqlite3

from scripts.durable_operations_gate import evaluate
from scripts.durable_research_state import DurableResearchState
import hashlib

from scripts.research_job_queue import _canonical


def frozen_request():
    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/frozen-contract.md",
        "frozen_spec_sha256": "1" * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40, "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31", "status": "QUEUED_NOT_EXECUTED",
    }
    return {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}



def test_missing_db_does_not_get_created(tmp_path):
    path = tmp_path / "missing.sqlite3"
    code, result = evaluate(path)
    assert code == 3
    assert result["status"] == "INVALID"
    assert not path.exists()


def test_healthy_queue_reports_metadata_only_and_does_not_mutate(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = DurableResearchState(path)
    request = frozen_request()
    store.ingest_record(request)
    before = store.status(request["fingerprint"])
    code, result = evaluate(path, now_ms=1000)
    assert code == 0
    assert result["status"] == "HEALTHY"
    assert result["research_edge_proven"] is False
    assert result["operations"]["accepted_results"] == "NOT_IMPLEMENTED"
    assert store.status(request["fingerprint"]) == before


def test_expired_lease_requires_operator_attention_without_requeue(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = DurableResearchState(path)
    ident = store.ingest_record(frozen_request())
    claim = store.claim_next("worker-A", lease_seconds=1, now_ms=1000)
    code, result = evaluate(path, now_ms=2001)
    assert code == 2
    assert result["status"] == "OPERATOR_ATTENTION"
    assert result["operations"]["expired_active_or_cancel_leases"] == 1
    assert store.status(ident)["attempt_id"] == claim["attempt_id"]
    assert store.status(ident)["state"] == "RUNNING"


def test_corrupted_metadata_fails_closed(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = DurableResearchState(path)
    ident = store.ingest_record(frozen_request())
    with sqlite3.connect(path) as db:
        db.execute("UPDATE jobs SET fencing_token=99 WHERE request_id=?", (ident,))
    code, result = evaluate(path, now_ms=1000)
    assert code == 3
    assert result["status"] == "INVALID"


def test_quarantined_job_is_not_reported_as_healthy(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = DurableResearchState(path)
    ident = store.ingest_record(frozen_request())
    claim = store.claim_next("worker-A", lease_seconds=10, now_ms=1000)
    store.quarantine(ident, claim["attempt_id"], claim["fencing_token"],
                     "worker-A", now_ms=1001)
    code, result = evaluate(path, now_ms=1002)
    assert code == 2
    assert result["operations"]["by_state"]["QUARANTINED"] == 1


def test_gate_audit_and_inventory_share_one_consistent_wal_snapshot(tmp_path, monkeypatch):
    """A concurrent committed change cannot enter the inventory unaudited."""
    path = tmp_path / "state.sqlite3"
    store = DurableResearchState(path)
    ident = store.ingest_record(frozen_request())
    original = DurableResearchState.audit_integrity
    observed = []

    def concurrent_writer_after_audit(self):
        result = original(self)
        # A second connection can commit while the read-only gate is open
        # because this database uses WAL. It must not change the gate's
        # already established read snapshot.
        with sqlite3.connect(path, timeout=5) as writer:
            writer.execute("UPDATE jobs SET state='QUARANTINED' WHERE request_id=?",
                           (ident,))
            writer.commit()
        observed.append("committed")
        return result

    monkeypatch.setattr(DurableResearchState, "audit_integrity",
                        concurrent_writer_after_audit)
    code, payload = evaluate(path, now_ms=1000)
    assert observed == ["committed"]
    assert code == 0
    assert payload["operations"]["by_state"] == {"QUEUED": 1}
    # The external writer did commit; only the gate's consistent view is old.
    assert store.status(ident)["state"] == "QUARANTINED"
