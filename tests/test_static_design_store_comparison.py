"""Synthetic-only audited store comparison regressions."""
import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_static_adapter_designs import stage_static_adapter_designs
from scripts.static_adapter_envelope import SCHEMA
from scripts.static_external_adapter_registry import REGISTRY
from scripts.static_design_store_comparison import compare_audited_static_design_stores


def _batch(request_id):
    name, spec = next(iter(REGISTRY.items()))
    return [{"schema": SCHEMA, "adapter": name, "request_id": request_id,
             "payload_schema": spec.inputs[0],
             "payload": {"field_names": ["synthetic_column"]}}]


def test_empty_stores_are_inert(tmp_path):
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    result = compare_audited_static_design_stores(old, new)
    assert result["continuity_preserved"] is True
    assert result["review_required"] is False
    assert result["snapshots_audited"] is True
    assert result["provenance_verified"] is False
    assert result["execution_authorized"] is False


def test_added_record_requires_review_without_jobs(tmp_path):
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    stage_static_adapter_designs(new, _batch("synthetic_added"))
    result = compare_audited_static_design_stores(old, new)
    assert (result["added"], result["removed"], result["modified"]) == (1, 0, 0)
    assert result["review_required"] is True
    with new._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_removed_record_requires_review(tmp_path):
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    stage_static_adapter_designs(old, _batch("synthetic_removed"))
    result = compare_audited_static_design_stores(old, new)
    assert result["removed"] == 1
    assert result["continuity_preserved"] is False


def test_corrupted_current_store_fails_closed(tmp_path):
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    stage_static_adapter_designs(new, _batch("synthetic_bad"))
    with new._write() as db:
        db.execute("UPDATE static_adapter_designs SET manifest_json='{}'")
    with pytest.raises(ValueError):
        compare_audited_static_design_stores(old, new)


def test_corrupted_previous_store_fails_closed(tmp_path):
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    stage_static_adapter_designs(old, _batch("synthetic_bad"))
    with old._write() as db:
        db.execute("DROP TABLE static_adapter_request_ids")
    with pytest.raises(ValueError):
        compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("old,new", [(None, None), (None, object()), (object(), None)])
def test_invalid_store_types_rejected(old, new):
    with pytest.raises(ValueError):
        compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("alias", ["same_object", "same_path", "hardlink"])
def test_same_physical_store_cannot_claim_independent_continuity(tmp_path, alias):
    import os

    old = DurableResearchState(tmp_path / "baseline.sqlite3")
    stage_static_adapter_designs(old, _batch("synthetic_baseline"))
    if alias == "same_object":
        current = old
    elif alias == "same_path":
        current = DurableResearchState(old.database)
    else:
        linked = tmp_path / "alias.sqlite3"
        os.link(old.database, linked)
        # Constructing a second state would alter the linked SQLite file;
        # compare the existing store with an alias object instead.
        current = object.__new__(DurableResearchState)
        current.database = linked
    with pytest.raises(ValueError, match="distinct SQLite stores"):
        compare_audited_static_design_stores(old, current)


@pytest.mark.parametrize("missing_side", ["baseline", "current"])
def test_missing_store_path_fails_closed_with_validation_error(tmp_path, missing_side):
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    missing = old if missing_side == "baseline" else new
    missing.database.unlink()
    with pytest.raises(ValueError, match="Cannot verify both SQLite store paths"):
        compare_audited_static_design_stores(old, new)


def test_invalid_store_path_type_fails_closed(tmp_path):
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    new.database = None
    with pytest.raises(ValueError, match="Cannot verify both SQLite store paths"):
        compare_audited_static_design_stores(old, new)


def test_path_replacement_during_snapshot_fails_closed(tmp_path, monkeypatch):
    import os
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    replacement = DurableResearchState(tmp_path / "replacement.sqlite3")
    original_snapshot = comparison.snapshot_static_design_records
    calls = 0

    def replacing_snapshot(state):
        nonlocal calls
        result = original_snapshot(state)
        calls += 1
        if calls == 1:
            os.replace(replacement.database, old.database)
        return result

    monkeypatch.setattr(comparison, "snapshot_static_design_records", replacing_snapshot)
    with pytest.raises(ValueError, match="path changed during comparison"):
        comparison.compare_audited_static_design_stores(old, new)


def test_directory_store_path_fails_closed(tmp_path):
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    new.database = tmp_path
    with pytest.raises(ValueError, match="Cannot verify both SQLite store paths"):
        compare_audited_static_design_stores(old, new)


def test_in_place_metadata_mutation_during_snapshot_fails_closed(tmp_path, monkeypatch):
    import os
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    original_snapshot = comparison.snapshot_static_design_records
    calls = 0

    def changing_snapshot(state):
        nonlocal calls
        result = original_snapshot(state)
        calls += 1
        if calls == 1:
            before = os.stat(old.database)
            os.utime(old.database, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
        return result

    monkeypatch.setattr(comparison, "snapshot_static_design_records", changing_snapshot)
    with pytest.raises(ValueError, match="metadata changed during comparison"):
        comparison.compare_audited_static_design_stores(old, new)


def test_unchanged_distinct_stores_still_compare(tmp_path):
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    result = compare_audited_static_design_stores(old, new)
    assert result["snapshots_audited"] is True
    assert result["execution_authorized"] is False


def test_wal_only_mutation_during_snapshot_fails_closed(tmp_path, monkeypatch):
    """A WAL change must invalidate evidence even if the main DB is untouched."""
    import os
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    original = comparison.snapshot_static_design_records
    calls = 0

    def mutating_snapshot(state):
        nonlocal calls
        result = original(state)
        calls += 1
        if calls == 1:
            # Synthetic sidecar mutation, not a real database write or research run.
            with open(os.fspath(old.database) + "-wal", "ab") as sidecar:
                sidecar.write(b"synthetic-wal-change")
        return result

    monkeypatch.setattr(comparison, "snapshot_static_design_records", mutating_snapshot)
    with pytest.raises(ValueError, match="WAL sidecar changed"):
        comparison.compare_audited_static_design_stores(old, new)


def test_wal_sidecar_directory_fails_closed(tmp_path):
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    (tmp_path / "old.sqlite3-wal").mkdir()
    with pytest.raises(ValueError, match="WAL sidecar must be a regular file"):
        compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("mutated_side", ["baseline", "current"])
def test_real_sqlite_wal_commit_during_snapshot_fails_closed(tmp_path, monkeypatch, mutated_side):
    """Synthetic SQLite transaction, no research or trading engine involved."""
    import sqlite3
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    # Exercise both independently opened stores: either side can mutate.
    target = old if mutated_side == "baseline" else new
    # Keep a connection open so SQLite retains the WAL sidecar across reads.
    writer = sqlite3.connect(target.database)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() == "wal"
        writer.execute("PRAGMA user_version=1")
        writer.commit()
        original = comparison.snapshot_static_design_records
        calls = 0

        def commit_between_snapshots(state):
            nonlocal calls
            snapshot = original(state)
            calls += 1
            if (mutated_side == "baseline" and calls == 1) or (mutated_side == "current" and calls == 2):
                writer.execute("PRAGMA user_version=2")
                writer.commit()
            return snapshot

        monkeypatch.setattr(comparison, "snapshot_static_design_records", commit_between_snapshots)
        with pytest.raises(ValueError, match="WAL sidecar changed"):
            comparison.compare_audited_static_design_stores(old, new)
    finally:
        writer.close()
