"""Real OS fault paths on fixed synthetic Python child, no vendor engines."""
import hashlib
import sys

import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_worker_process_supervisor import (
    LinuxProcInspector, recover_expired_process_after_exit,
)
from scripts.supervised_synthetic_fault_lab import supervised_synthetic_fault_probe
from scripts.research_job_queue import _canonical

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="Linux /proc only")


def claim_fixture(tmp_path):
    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/example.md",
        "frozen_spec_sha256": "1" * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40, "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31", "status": "QUEUED_NOT_EXECUTED",
    }
    record = {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}
    store = DurableResearchState(tmp_path / "state.sqlite3")
    store.ingest_record(record)
    claim = store.claim_next("synthetic-worker", lease_seconds=10, now_ms=1000)
    return store, claim, record


@pytest.mark.parametrize("fault,expected", [
    ("digest", "SYNTHETIC_SUCCESS_ONLY"),
    ("nonzero", "FAILED_NONZERO_EXIT"),
    ("stderr", "FAILED_NONZERO_EXIT"),
    ("flood", "FAILED_OUTPUT_BOUND"),
    ("stall", "FAILED_WALL_DEADLINE"),
])
def test_real_process_fault_paths_have_bound_output_and_proven_exit(
    tmp_path, fault, expected,
):
    store, claim, record = claim_fixture(tmp_path)
    result = supervised_synthetic_fault_probe(
        store, claim, now_ms=1200, fault=fault,
        wall_seconds=1 if fault == "stall" else 2)
    assert result["result"] == expected
    assert result["process_group_exit_proven"] is True
    assert result["stdout_bytes"] <= 1024
    assert result["stderr_bytes"] <= 1024
    assert result["vendor_engine_executed"] is False
    assert result["market_data_accessed"] is False
    assert result["research_result_accepted"] is False
    assert result["automatic_retry_triggered"] is False
    assert store.status(record["fingerprint"])["state"] == "RUNNING"


@pytest.mark.parametrize("options", [
    {"fault": "arbitrary_command"},
    {"wall_seconds": 0}, {"wall_seconds": True},
    {"wall_seconds": 11},
])
def test_unsanctioned_fault_probe_blocked_before_spawn(tmp_path, options):
    store, claim, record = claim_fixture(tmp_path)
    with pytest.raises(ValueError, match="Only bounded"):
        supervised_synthetic_fault_probe(
            store, claim, now_ms=1200, **options)
    with store._connection() as db:
        assert db.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
            " AND name='supervisor_process_identity'").fetchone()[0] == 0


def test_stale_fenced_attempt_cannot_spawn_fault_lab_worker(tmp_path):
    store, claim, record = claim_fixture(tmp_path)
    stale = dict(claim, fencing_token=claim["fencing_token"] + 1)
    with pytest.raises(ValueError, match="Stale"):
        supervised_synthetic_fault_probe(store, stale, now_ms=1200)
    assert store.status(record["fingerprint"])["state"] == "RUNNING"


def test_failed_synthetic_process_recovery_needs_proven_exit_and_expiry(tmp_path):
    store, claim, record = claim_fixture(tmp_path)
    result = supervised_synthetic_fault_probe(
        store, claim, now_ms=1200, fault="nonzero")
    assert result["result"] == "FAILED_NONZERO_EXIT"
    with pytest.raises(ValueError, match="No expired"):
        recover_expired_process_after_exit(
            store, record["fingerprint"], LinuxProcInspector(), now_ms=10999)
    assert recover_expired_process_after_exit(
        store, record["fingerprint"], LinuxProcInspector(), now_ms=11001)
    assert store.status(record["fingerprint"])["state"] == "QUEUED"
    next_claim = store.claim_next("new-worker", now_ms=11002)
    assert next_claim["fencing_token"] == claim["fencing_token"] + 1
