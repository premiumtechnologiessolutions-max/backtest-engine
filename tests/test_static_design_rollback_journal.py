"""Synthetic rollback-journal integrity checks; no research execution."""
import os

import pytest

import scripts.static_design_store_comparison as comparison
from scripts.durable_research_state import DurableResearchState


@pytest.mark.parametrize("side", ["previous", "current"])
def test_rollback_journal_created_during_continuity_is_rejected(tmp_path, monkeypatch, side):
    previous = DurableResearchState(tmp_path / "previous.sqlite3")
    current = DurableResearchState(tmp_path / "current.sqlite3")
    target = previous if side == "previous" else current
    original = comparison.verify_static_design_continuity

    def create_journal(before, after):
        result = original(before, after)
        with open(os.fspath(target.database) + "-journal", "wb") as handle:
            handle.write(b"synthetic-journal-only")
        return result

    monkeypatch.setattr(comparison, "verify_static_design_continuity", create_journal)
    with pytest.raises(ValueError, match="JOURNAL sidecar changed during comparison"):
        comparison.compare_audited_static_design_stores(previous, current)


@pytest.mark.parametrize("side", ["previous", "current"])
def test_rollback_journal_symlink_rejected_before_read(tmp_path, monkeypatch, side):
    previous = DurableResearchState(tmp_path / "previous.sqlite3")
    current = DurableResearchState(tmp_path / "current.sqlite3")
    target = previous if side == "previous" else current
    unrelated = tmp_path / "unrelated"
    unrelated.write_bytes(b"synthetic")
    os.symlink(unrelated, os.fspath(target.database) + "-journal")

    def must_not_read(_):
        pytest.fail("Snapshot read must not occur after journal preflight failure")

    monkeypatch.setattr(comparison, "snapshot_static_design_records", must_not_read)
    with pytest.raises(ValueError, match="JOURNAL sidecar must be a regular file"):
        comparison.compare_audited_static_design_stores(previous, current)


@pytest.mark.parametrize("side", ["previous", "current"])
def test_rollback_journal_external_hardlink_rejected_before_read(tmp_path, monkeypatch, side):
    """A journal with another directory entry is not an isolated audit input."""
    previous = DurableResearchState(tmp_path / "previous.sqlite3")
    current = DurableResearchState(tmp_path / "current.sqlite3")
    target = previous if side == "previous" else current
    unrelated = tmp_path / "external-journal"
    unrelated.write_bytes(b"synthetic-only")
    os.link(unrelated, os.fspath(target.database) + "-journal")

    def must_not_read(_):
        pytest.fail("Snapshot read must not occur after journal hardlink rejection")

    monkeypatch.setattr(comparison, "snapshot_static_design_records", must_not_read)
    with pytest.raises(ValueError, match="JOURNAL sidecar has external hardlink aliases"):
        comparison.compare_audited_static_design_stores(previous, current)
