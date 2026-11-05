"""Synthetic-only audited static design snapshot regressions."""
import pytest
from scripts.durable_research_state import DurableResearchState
from scripts.durable_static_adapter_designs import stage_static_adapter_designs
from scripts.static_design_inventory import snapshot_static_design_records
from scripts.static_design_continuity import verify_static_design_continuity
from scripts.static_adapter_envelope import SCHEMA
from scripts.static_external_adapter_registry import REGISTRY

def batch(request_id):
    name, spec = next(iter(REGISTRY.items()))
    return [{"schema": SCHEMA, "adapter": name, "request_id": request_id,
             "payload_schema": spec.inputs[0],
             "payload": {"field_names": ["synthetic_column"]}}]

def test_audited_snapshot_is_stable_and_inert(tmp_path):
    state = DurableResearchState(tmp_path / "synthetic.sqlite3")
    assert snapshot_static_design_records(state) == []
    stage_static_adapter_designs(state, batch("synthetic_a"))
    before = snapshot_static_design_records(state)
    assert before == snapshot_static_design_records(state)
    assert len(before) == 1 and len(before[0]["payload_sha256"]) == 64
    assert verify_static_design_continuity(before, before)["continuity_preserved"]
    stage_static_adapter_designs(state, batch("synthetic_b"))
    report = verify_static_design_continuity(before, snapshot_static_design_records(state))
    assert report["added"] == 1 and report["removed"] == 0
    assert report["execution_authorized"] is False
    with state._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0

def test_corrupt_manifest_refuses_snapshot(tmp_path):
    state = DurableResearchState(tmp_path / "synthetic.sqlite3")
    stage_static_adapter_designs(state, batch("synthetic_a"))
    with state._write() as db:
        db.execute("UPDATE static_adapter_designs SET manifest_json='{}'")
    with pytest.raises(ValueError):
        snapshot_static_design_records(state)

def test_missing_index_refuses_snapshot(tmp_path):
    state = DurableResearchState(tmp_path / "synthetic.sqlite3")
    stage_static_adapter_designs(state, batch("synthetic_a"))
    with state._write() as db:
        db.execute("DROP TABLE static_adapter_request_ids")
    with pytest.raises(ValueError):
        snapshot_static_design_records(state)

def test_invalid_state_refused():
    with pytest.raises(ValueError):
        snapshot_static_design_records(None)
