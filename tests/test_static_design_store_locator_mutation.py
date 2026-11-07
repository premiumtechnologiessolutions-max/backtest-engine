"""Synthetic regressions for mutable SQLite store locator identity."""
import os

import pytest

from scripts.durable_research_state import DurableResearchState
import scripts.static_design_store_comparison as comparison


@pytest.mark.parametrize("side", ["baseline", "current"])
@pytest.mark.parametrize("phase", ["snapshot", "verification"])
def test_store_locator_rewrite_during_audit_fails_closed(tmp_path, monkeypatch, side, phase):
    old = DurableResearchState(tmp_path / "old.sqlite3")
    new = DurableResearchState(tmp_path / "new.sqlite3")
    target = old if side == "baseline" else new
    original_path = os.fspath(target.database)

    def rewrite():
        # Same physical inode and same canonical absolute path: only the
        # mutable locator changes. Metadata/parent checks alone miss this.
        target.database = os.path.dirname(original_path) + "/./" + os.path.basename(original_path)

    if phase == "verification":
        original = comparison.verify_static_design_continuity

        def changed(before, after):
            result = original(before, after)
            rewrite()
            return result

        monkeypatch.setattr(comparison, "verify_static_design_continuity", changed)
    else:
        original = comparison.snapshot_static_design_records

        def changed(state):
            result = original(state)
            if state is target:
                rewrite()
            return result

        monkeypatch.setattr(comparison, "snapshot_static_design_records", changed)

    with pytest.raises(ValueError, match="locator changed during comparison"):
        comparison.compare_audited_static_design_stores(old, new)
