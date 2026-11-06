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
    # External hardlinks are rejected before the distinct-store identity check.
    expected_error = "external hardlink aliases" if alias == "hardlink" else "distinct SQLite stores"
    with pytest.raises(ValueError, match=expected_error):
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
    with pytest.raises(ValueError, match="Cannot verify SQLite store parent directories"):
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


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_wal_symlink_is_rejected_before_snapshot(tmp_path, side):
    """A WAL symlink must not be trusted as an ordinary SQLite sidecar."""
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    target = old if side == "baseline" else new
    foreign = tmp_path / "unrelated-wal"
    foreign.write_bytes(b"synthetic-only")
    import os
    os.symlink(foreign, os.fspath(target.database) + "-wal")
    with pytest.raises(ValueError, match="WAL sidecar must be a regular file"):
        compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_main_database_symlink_rejected_before_snapshot(tmp_path, monkeypatch, side):
    """An aliased database path is not independent audit evidence."""
    import os
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    target = old if side == "baseline" else new
    original = target.database
    alias = tmp_path / (side + "-alias.sqlite3")
    os.symlink(original, alias)
    target.database = alias

    def forbidden_snapshot(_state):
        pytest.fail("audit must reject symlink before reading records")

    monkeypatch.setattr(comparison, "snapshot_static_design_records", forbidden_snapshot)
    with pytest.raises(ValueError, match="Cannot verify both SQLite store paths"):
        comparison.compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_shm_symlink_rejected_before_snapshot(tmp_path, monkeypatch, side):
    """Synthetic shared-memory sidecar aliases must fail before any audit read."""
    import os
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    target = old if side == "baseline" else new
    foreign = tmp_path / "foreign-shm"
    foreign.write_bytes(b"synthetic")
    os.symlink(foreign, os.fspath(target.database) + "-shm")
    monkeypatch.setattr(comparison, "snapshot_static_design_records",
                        lambda _: pytest.fail("snapshot should not execute"))
    with pytest.raises(ValueError, match="SHM sidecar must be a regular file"):
        comparison.compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_shm_change_between_snapshots_fails_closed(tmp_path, monkeypatch, side):
    """A synthetic shared-memory sidecar change invalidates audit evidence."""
    import os
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    target = old if side == "baseline" else new
    original = comparison.snapshot_static_design_records
    calls = 0

    def mutate_after_snapshot(state):
        nonlocal calls
        result = original(state)
        calls += 1
        # Mutate the selected store only after its own snapshot completes.
        # Opening the current SQLite store can remove an unowned synthetic
        # SHM sidecar, so mutating it before that read is not a stable test.
        if (side == "baseline" and calls == 1) or (side == "current" and calls == 2):
            with open(os.fspath(target.database) + "-shm", "ab") as sidecar:
                sidecar.write(b"synthetic-shm-change")
        return result

    monkeypatch.setattr(comparison, "snapshot_static_design_records", mutate_after_snapshot)
    with pytest.raises(ValueError, match="SHM sidecar changed during comparison"):
        comparison.compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_main_store_mode_change_during_snapshot_fails_closed(tmp_path, monkeypatch, side):
    """A chmod during a synthetic audit invalidates the filesystem evidence."""
    import os
    import stat
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    target = old if side == "baseline" else new
    original = comparison.snapshot_static_design_records
    calls = 0

    def changing_snapshot(state):
        nonlocal calls
        result = original(state)
        calls += 1
        if (side == "baseline" and calls == 1) or (side == "current" and calls == 2):
            mode = stat.S_IMODE(os.lstat(target.database).st_mode)
            os.chmod(target.database, mode ^ stat.S_IXUSR)
        return result

    monkeypatch.setattr(comparison, "snapshot_static_design_records", changing_snapshot)
    with pytest.raises(ValueError, match="metadata changed during comparison"):
        comparison.compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_mutation_during_continuity_verification_fails_closed(tmp_path, monkeypatch, side):
    """Metadata checks must run after the potentially long verification step."""
    import os
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    target = old if side == "baseline" else new
    original = comparison.verify_static_design_continuity

    def mutate_during_verification(before, after):
        result = original(before, after)
        info = os.stat(target.database)
        os.utime(target.database, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
        return result

    monkeypatch.setattr(comparison, "verify_static_design_continuity", mutate_during_verification)
    with pytest.raises(ValueError, match="metadata changed during comparison"):
        comparison.compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
@pytest.mark.parametrize("alias_target", ["other_sidecar", "main_database"])
def test_hardlinked_sqlite_sidecar_alias_fails_before_snapshot(
    tmp_path, monkeypatch, suffix, alias_target
):
    """Hardlinks cannot establish independent SQLite audit evidence."""
    import os
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    target = (os.fspath(old.database) + "-wal" if alias_target == "other_sidecar"
              else os.fspath(old.database))
    if alias_target == "other_sidecar":
        with open(target, "wb") as handle:
            handle.write(b"synthetic-only")
    os.link(target, os.fspath(new.database) + suffix)
    monkeypatch.setattr(comparison, "snapshot_static_design_records",
                        lambda _: pytest.fail("must reject aliases before reading"))
    with pytest.raises(ValueError, match="external hardlink aliases|distinct physical files"):
        comparison.compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("side", ["baseline", "current"])
@pytest.mark.parametrize("suffix", ["", "-wal", "-shm"])
def test_external_hardlink_alias_rejected_before_snapshot(tmp_path, monkeypatch, side, suffix):
    """An alias outside the compared stores must not evade inode-pair checks."""
    import os
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    target = old if side == "baseline" else new
    path = os.fspath(target.database) + suffix
    if suffix:
        with open(path, "wb") as handle:
            handle.write(b"synthetic-sidecar")
    os.link(path, tmp_path / ("external-alias-" + side + suffix.lstrip("-")))
    monkeypatch.setattr(comparison, "snapshot_static_design_records",
                        lambda _: pytest.fail("must reject hardlinks before snapshot"))
    with pytest.raises(ValueError, match="external hardlink aliases"):
        comparison.compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_main_database_hardlink_added_during_verification_rejected(tmp_path, monkeypatch, side):
    """New external aliases invalidate the snapshot even without file writes."""
    import os
    import scripts.static_design_store_comparison as comparison

    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    target = old if side == "baseline" else new
    original = comparison.verify_static_design_continuity

    def add_alias(before, after):
        result = original(before, after)
        os.link(target.database, tmp_path / ("late-alias-" + side))
        return result

    monkeypatch.setattr(comparison, "verify_static_design_continuity", add_alias)
    with pytest.raises(ValueError, match="acquired external hardlink aliases"):
        comparison.compare_audited_static_design_stores(old, new)


@pytest.mark.parametrize("side", ["baseline", "current"])
def test_symlinked_parent_directory_rejected_before_snapshot(tmp_path, monkeypatch, side):
    """A regular database reached through an aliased parent is not trusted."""
    import os
    import scripts.static_design_store_comparison as comparison

    real = tmp_path / "real"
    real.mkdir()
    old = DurableResearchState(real / "old.sqlite3")
    new = DurableResearchState(real / "new.sqlite3")
    alias = tmp_path / "linked-parent"
    os.symlink(real, alias, target_is_directory=True)
    target = old if side == "baseline" else new
    target.database = alias / target.database.name
    monkeypatch.setattr(comparison, "snapshot_static_design_records",
                        lambda _: pytest.fail("must reject parent alias before reading"))
    with pytest.raises(ValueError, match="symlinked parent"):
        comparison.compare_audited_static_design_stores(old, new)
