"""OS-level lifecycle tests for ONE fixed synthetic child, not research."""
import hashlib
import sys

import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_worker_process_supervisor import (
    LinuxProcInspector, recover_expired_process_after_exit,
)
from scripts.synthetic_process_lifecycle_probe import (
    synthetic_process_lifecycle_probe,
)
from scripts.research_job_queue import _canonical

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux /proc only")


def case(tmp_path):
    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/example.md",
        "frozen_spec_sha256": "1" * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40,
        "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31",
        "status": "QUEUED_NOT_EXECUTED",
    }
    record = {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}
    store = DurableResearchState(tmp_path / "state.sqlite3")
    store.ingest_record(record)
    claim = store.claim_next("synthetic-worker", lease_seconds=10, now_ms=1000)
    return store, record, claim


def test_real_isolated_linux_process_is_attested_and_exits(tmp_path):
    store, record, claim = case(tmp_path)
    evidence = synthetic_process_lifecycle_probe(
        store, claim, now_ms=1100)
    assert evidence["pid"] == evidence["process_group"]
    assert evidence["process_group_exit_proven"] is True
    assert evidence["research_engine_started"] is False
    assert evidence["market_data_read"] is False
    assert evidence["network_namespace_enforced"] is False
    assert evidence["research_result_accepted"] is False
    assert store.status(record["fingerprint"])["state"] == "RUNNING"
    with store._connection() as db:
        bound = db.execute(
            "SELECT start_ticks FROM supervisor_process_identity"
            " WHERE attempt_id=?", (claim["attempt_id"],)
        ).fetchone()
    assert bound["start_ticks"] == evidence["start_ticks"]


def test_synthetic_exit_identity_safely_requeues_after_lease(tmp_path):
    store, record, claim = case(tmp_path)
    synthetic_process_lifecycle_probe(store, claim, now_ms=1500)
    assert recover_expired_process_after_exit(
        store, record["fingerprint"], LinuxProcInspector(), now_ms=11001)
    assert store.status(record["fingerprint"])["state"] == "QUEUED"
    next_claim = store.claim_next("new-worker", now_ms=11002)
    assert next_claim["fencing_token"] == claim["fencing_token"] + 1


@pytest.mark.parametrize("options", [
    {"mode": "RUN_REAL_BACKTEST"}, {"timeout_seconds": 0},
    {"timeout_seconds": True}, {"timeout_seconds": 100},
])
def test_unsanctioned_rehearsal_contract_fails_before_spawn(tmp_path, options):
    store, record, claim = case(tmp_path)
    with pytest.raises(ValueError, match="Fixed Linux"):
        synthetic_process_lifecycle_probe(store, claim, now_ms=1500, **options)
    assert store.status(record["fingerprint"])["state"] == "RUNNING"
    with store._connection() as db:
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name='supervisor_process_identity'").fetchall()
        assert not rows


def test_stale_claim_cannot_launch_synthetic_process(tmp_path):
    store, record, claim = case(tmp_path)
    stale = dict(claim, fencing_token=claim["fencing_token"] + 1)
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        synthetic_process_lifecycle_probe(store, stale, now_ms=1500)
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        synthetic_process_lifecycle_probe(store, claim, now_ms=11001)
    assert store.status(record["fingerprint"])["attempt_id"] == claim["attempt_id"]
