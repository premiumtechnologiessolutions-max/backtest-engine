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
