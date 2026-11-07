"""Synthetic-only SQLite backup and restore with WAL, receipts and mutations."""
import hashlib
import json
import sqlite3

import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_backup_attestation import (
    backup_durable_state, restore_durable_backup, verify_durable_backup,
)
from scripts.research_job_queue import _canonical
from scripts.durable_operations_gate import evaluate
from scripts.unverified_receipt_inbox import UnverifiedReceiptInbox
from norisk_quant.external_queue_binding import bind_claim
from norisk_quant.external_research_bridge import result_receipt


def frozen(seed="1"):
    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/example.md",
        "frozen_spec_sha256": seed * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40, "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31", "status": "QUEUED_NOT_EXECUTED",
    }
    return {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}


def setup(tmp_path, with_receipt=False):
    store = DurableResearchState(tmp_path / "working.sqlite3")
    records = [frozen("1"), frozen("3")]
    for record in records:
        store.ingest_record(record)
    claim = store.claim_next("worker-A", now_ms=1000, lease_seconds=1000)
    if with_receipt:
        store.start_reconciliation(records[0]["fingerprint"],
                                   claim["attempt_id"], claim["fencing_token"],
                                   claim["worker"], now_ms=1100)
        binding = bind_claim(records[0], claim, engine="lean",
                             source_sha256="4" * 64,
                             code_sha256="5" * 64)
        receipt = result_receipt(
            binding["external_request"], provider_build_sha256="6" * 64,
            artifact_sha256="7" * 64, status="completed_unverified")
        UnverifiedReceiptInbox(store).stage(
            records[0], claim, binding, receipt,
            actual_artifact_sha256="7" * 64, now_ms=1200)
    root = tmp_path / "backups"
    root.mkdir()
    return store, records, claim, root


def test_backup_restores_jobs_attempts_and_fences_without_execution(tmp_path):
    store, records, claim, root = setup(tmp_path)
    before = [store.status(r["fingerprint"]) for r in records]
    made = backup_durable_state(store.database, root, "synthetic_001",
                                now_ms=1500)
    assert made["worker_started"] is False
    assert made["attempts_observed"] == 1
    check = verify_durable_backup(root / "synthetic_001")
    assert check["jobs_observed"] == 2
    result = restore_durable_backup(
        root / "synthetic_001", tmp_path / "restored.sqlite3")
    assert result["automatic_resume"] is False
    recovered = DurableResearchState(tmp_path / "restored.sqlite3")
    after = [recovered.status(r["fingerprint"]) for r in records]
    assert after == before
    assert after[0]["state"] == "RUNNING"
    with recovered._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3
    assert evaluate(recovered.database, now_ms=1500)[0] == 0


def test_wal_receipt_state_is_captured_without_forcing_market_run(tmp_path):
    store, records, claim, root = setup(tmp_path, with_receipt=True)
    # A held read connection makes WAL pages a realistic snapshot condition.
    with sqlite3.connect(store.database) as observer:
        observer.execute("BEGIN")
        observer.execute("SELECT COUNT(*) FROM jobs").fetchone()
        result = backup_durable_state(
            store.database, root, "receipt_copy", now_ms=1500)
        assert result["health_gate_code"] == 2
    output = tmp_path / "restored.sqlite3"
    restore_durable_backup(root / "receipt_copy", output)
    with sqlite3.connect(output) as db:
        assert db.execute("SELECT COUNT(*) FROM unverified_receipts").fetchone()[0] == 1
    assert evaluate(output, now_ms=1500)[0] == 2


def test_tampered_snapshot_and_manifest_are_rejected(tmp_path):
    store, _, _, root = setup(tmp_path)
    backup_durable_state(store.database, root, "tamper_001", now_ms=1500)
    snapshot = root / "tamper_001"
    (snapshot / "manifest.json").write_text(
        (snapshot / "manifest.json").read_text().replace(
            "VERIFIED_CONTROL_STATE_ONLY", "AUTO_EXECUTE"),
        encoding="utf-8")
    with pytest.raises(ValueError):
        verify_durable_backup(snapshot)
    with pytest.raises(ValueError):
        restore_durable_backup(snapshot, tmp_path / "should_not_exist.sqlite3")
    assert not (tmp_path / "should_not_exist.sqlite3").exists()


def test_modified_snapshot_bytes_fail_digest(tmp_path):
    store, _, _, root = setup(tmp_path)
    backup_durable_state(store.database, root, "tamper_002", now_ms=1500)
    snapshot = root / "tamper_002"
    with (snapshot / "state.sqlite3").open("ab") as out:
        out.write(b"MUTATED")
    with pytest.raises(ValueError, match="bytes diverge"):
        verify_durable_backup(snapshot)


def test_same_snapshot_id_and_existing_restore_destination_refused(tmp_path):
    store, _, _, root = setup(tmp_path)
    backup_durable_state(store.database, root, "immutable", now_ms=1500)
    with pytest.raises(ValueError, match="already exists"):
        backup_durable_state(store.database, root, "immutable", now_ms=1500)
    target = tmp_path / "do_not_overwrite.sqlite3"
    target.write_bytes(b"MY_OWN_FILE")
    with pytest.raises(ValueError, match="new non-symlink"):
        restore_durable_backup(root / "immutable", target)
    assert target.read_bytes() == b"MY_OWN_FILE"


def test_incomplete_backup_directory_does_not_restore(tmp_path):
    partial = tmp_path / "partial"
    partial.mkdir()
    (partial / "state.sqlite3").write_bytes(b"not a database")
    with pytest.raises(ValueError):
        verify_durable_backup(partial)


def test_source_is_not_modified_by_backup(tmp_path):
    store, records, claim, root = setup(tmp_path)
    original = [store.status(r["fingerprint"]) for r in records]
    backup_durable_state(store.database, root, "readonly_backup", now_ms=1500)
    assert [store.status(r["fingerprint"]) for r in records] == original
    assert store.status(records[0]["fingerprint"])["attempt_id"] == claim["attempt_id"]


def test_symlinked_source_backup_root_and_target_refused(tmp_path):
    store, records, claim, root = setup(tmp_path)
    source_alias = tmp_path / "shortcut.sqlite3"
    try:
        source_alias.symlink_to(store.database)
    except OSError:
        pytest.skip("Symlink support unavailable")
    with pytest.raises(ValueError, match="Unsafe"):
        backup_durable_state(source_alias, root, "alias", now_ms=1500)
    assert not (root / "alias").exists()
    backup_durable_state(store.database, root, "original", now_ms=1500)
    dest = tmp_path / "restore_alias.sqlite3"
    dest.symlink_to(store.database)
    with pytest.raises(ValueError, match="new non-symlink"):
        restore_durable_backup(root / "original", dest)


def test_manifest_duplicate_keys_are_refused(tmp_path):
    store, _, _, root = setup(tmp_path)
    backup_durable_state(store.database, root, "duplicate", now_ms=1500)
    manifest = root / "duplicate" / "manifest.json"
    manifest.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        verify_durable_backup(root / "duplicate")
