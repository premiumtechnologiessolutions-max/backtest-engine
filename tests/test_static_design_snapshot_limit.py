"""Synthetic regression: bounded audited inventory snapshots."""
import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_static_adapter_designs import stage_static_adapter_designs
from scripts.static_adapter_envelope import SCHEMA
from scripts.static_external_adapter_registry import REGISTRY
import scripts.static_design_inventory as inventory


def test_snapshot_rejects_oversized_audited_count_before_envelope_read(tmp_path, monkeypatch):
    state = DurableResearchState(tmp_path / "synthetic.sqlite3")
    name, spec = next(iter(REGISTRY.items()))
    stage_static_adapter_designs(state, [{
        "schema": SCHEMA, "adapter": name, "request_id": "synthetic_only",
        "payload_schema": spec.inputs[0],
        "payload": {"field_names": ["synthetic_column"]},
    }])
    # Simulate a successfully audited, oversized inbox without creating
    # thousands of records. The guard must run before materializing envelopes.
    monkeypatch.setattr(inventory, "_audit", lambda db: {"requests": 10001, "batches": 1})
    with pytest.raises(ValueError, match="exceeds continuity limit"):
        inventory.snapshot_static_design_records(state)


def test_snapshot_limit_does_not_change_normal_audited_reads(tmp_path):
    state = DurableResearchState(tmp_path / "synthetic.sqlite3")
    assert inventory.snapshot_static_design_records(state) == []
