"""Synthetic rollback journal mutation tests; never run research engines or datasets."""
import os

import pytest

import scripts.static_design_store_comparison as comparison
from scripts.durable_research_state import DurableResearchState


@pytest.mark.parametrize("side", ["previous", "current"])
def test_existing_rollback_journal_in_place_mutation_rejected(tmp_path, monkeypatch, side):
    previous = DurableResearchState(tmp_path / "previous.sqlite3")
    current = DurableResearchState(tmp_path / "current.sqlite3")
    target = previous if side == "previous" else current
    journal = os.fspath(target.database) + "-journal"
    with open(journal, "wb") as handle:
        handle.write(b"synthetic-journal")
    original = comparison.verify_static_design_continuity

    def mutate(before, after):
        result = original(before, after)
        with open(journal, "ab") as handle:
            handle.write(b"-changed")
        return result

    monkeypatch.setattr(comparison, "verify_static_design_continuity", mutate)
    with pytest.raises(ValueError, match="JOURNAL sidecar changed during comparison"):
        comparison.compare_audited_static_design_stores(previous, current)


@pytest.mark.parametrize("side", ["previous", "current"])
def test_existing_rollback_journal_removed_during_audit_rejected(tmp_path, monkeypatch, side):
    previous = DurableResearchState(tmp_path / "previous.sqlite3")
    current = DurableResearchState(tmp_path / "current.sqlite3")
    target = previous if side == "previous" else current
    journal = os.fspath(target.database) + "-journal"
    with open(journal, "wb") as handle:
        handle.write(b"synthetic-journal")
    original = comparison.verify_static_design_continuity

    def remove(before, after):
        result = original(before, after)
        # SQLite may itself remove a synthetic rollback journal while opening
        # the read-only snapshot. Either disappearance must fail the audit.
        if os.path.lexists(journal):
            os.unlink(journal)
        return result

    monkeypatch.setattr(comparison, "verify_static_design_continuity", remove)
    with pytest.raises(ValueError, match="JOURNAL sidecar changed during comparison"):
        comparison.compare_audited_static_design_stores(previous, current)
