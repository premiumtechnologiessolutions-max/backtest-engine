"""No worker is launched: synthetic fake OS inspector + SQLite lease tests."""
import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_worker_process_supervisor import (
    ProcessIdentity, attach_process_identity,
    recover_expired_process_after_exit,
)
from scripts.research_job_queue import _canonical

BOOT = "11111111-2222-3333-4444-555555555555"


class FakeInspector:
    def __init__(self, status="ACTIVE", *, pid=5001, ticks=9000):
        self.status = status
        self.pid = pid
        self.ticks = ticks

    def capture(self, pid):
        assert pid == self.pid
        return ProcessIdentity(BOOT, pid, pid, self.ticks)

    def observe_exit(self, identity):
        assert identity.pid == self.pid
        return self.status


def scenario(tmp_path):
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
    claim = store.claim_next("worker-A", lease_seconds=1, now_ms=1000)
    return store, record, claim


def test_process_group_identity_validated():
    with pytest.raises(ValueError):
        ProcessIdentity(BOOT, 123, 456, 50)
    with pytest.raises(ValueError):
        ProcessIdentity(BOOT, True, True, 50)
    with pytest.raises(ValueError):
        ProcessIdentity(BOOT, 123, 123, 0)
    with pytest.raises(ValueError):
        ProcessIdentity("made-up-host", 123, 123, 100)


def test_lease_expiry_alone_never_allows_verified_requeue(tmp_path):
    store, record, claim = scenario(tmp_path)
    fake = FakeInspector("ACTIVE")
    with pytest.raises(ValueError, match="No authenticated"):
        recover_expired_process_after_exit(
            store, record["fingerprint"], fake, now_ms=2001)
    attach_process_identity(store, claim, 5001, fake, now_ms=1050)
    with pytest.raises(ValueError, match="not proven"):
        recover_expired_process_after_exit(
            store, record["fingerprint"], fake, now_ms=2001)
    assert store.status(record["fingerprint"])["state"] == "RUNNING"


def test_proven_exit_requeues_without_running_new_worker(tmp_path):
    store, record, claim = scenario(tmp_path)
    fake = FakeInspector()
    result = attach_process_identity(store, claim, 5001, fake, now_ms=1100)
    assert result["research_executed"] is False
    fake.status = "EXITED_SAME_BOOT_NO_GROUP_MEMBERS"
    with pytest.raises(ValueError, match="No expired"):
        recover_expired_process_after_exit(
            store, record["fingerprint"], fake, now_ms=1999)
    assert recover_expired_process_after_exit(
        store, record["fingerprint"], fake, now_ms=2001)
    assert store.status(record["fingerprint"])["state"] == "QUEUED"
    new = store.claim_next("worker-B", now_ms=2100)
    assert new["fencing_token"] == claim["fencing_token"] + 1
    with pytest.raises(ValueError, match="No expired"):
        recover_expired_process_after_exit(
            store, record["fingerprint"], fake, now_ms=2101)


@pytest.mark.parametrize("status", [
    "ACTIVE", "UNKNOWN_BOOT_CHANGED", "UNKNOWN_PROC_STATUS"])
def test_unknown_or_live_os_identity_blocks_recovery(tmp_path, status):
    store, record, claim = scenario(tmp_path)
    fake = FakeInspector()
    attach_process_identity(store, claim, 5001, fake, now_ms=1100)
    fake.status = status
    with pytest.raises(ValueError, match="not proven"):
        recover_expired_process_after_exit(
            store, record["fingerprint"], fake, now_ms=2001)
    assert store.status(record["fingerprint"])["attempt_id"] == claim["attempt_id"]


def test_attempt_identity_can_never_be_replaced_mid_lease(tmp_path):
    store, record, claim = scenario(tmp_path)
    fake = FakeInspector()
    attach_process_identity(store, claim, 5001, fake, now_ms=1050)
    assert attach_process_identity(
        store, claim, 5001, fake, now_ms=1051)["research_executed"] is False
    fake.ticks = 9999
    with pytest.raises(ValueError, match="identity drift"):
        attach_process_identity(store, claim, 5001, fake, now_ms=1052)


def test_process_exit_requeue_is_single_winner_under_race(tmp_path):
    store, record, claim = scenario(tmp_path)
    fake = FakeInspector()
    attach_process_identity(store, claim, 5001, fake, now_ms=1050)
    fake.status = "EXITED_SAME_BOOT_NO_GROUP_MEMBERS"
    def attempt(_):
        try:
            return recover_expired_process_after_exit(
                store, record["fingerprint"], fake, now_ms=2001)
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(attempt, range(3)))
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 2
    assert store.status(record["fingerprint"])["state"] == "QUEUED"


def test_unattached_and_cancel_requested_attempts_never_requeue(tmp_path):
    store, record, claim = scenario(tmp_path)
    fake = FakeInspector()
    attach_process_identity(store, claim, 5001, fake, now_ms=1050)
    store.cancel(record["fingerprint"])
    fake.status = "EXITED_SAME_BOOT_NO_GROUP_MEMBERS"
    with pytest.raises(ValueError, match="No expired"):
        recover_expired_process_after_exit(
            store, record["fingerprint"], fake, now_ms=2001)


def test_linux_stat_parser_handles_complex_command_name():
    from scripts.durable_worker_process_supervisor import LinuxProcInspector
    fields = ["S", "1", "8080"] + ["0"] * 16 + ["12345"] + ["0"] * 5
    state, pgrp, start = LinuxProcInspector._stat(
        "8080 (complex (name) with spaces) " + " ".join(fields))
    assert (state, pgrp, start) == ("S", 8080, 12345)
