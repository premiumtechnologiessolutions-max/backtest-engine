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


def test_snapshot_rejects_excess_rows_before_audit_materialization(tmp_path, monkeypatch):
    state = DurableResearchState(tmp_path / "synthetic.sqlite3")
    name, spec = next(iter(REGISTRY.items()))
    stage_static_adapter_designs(state, [{
        "schema": SCHEMA, "adapter": name, "request_id": "synthetic_seed",
        "payload_schema": spec.inputs[0],
        "payload": {"field_names": ["synthetic_column"]},
    }])
    # Deliberately corrupt only a synthetic inbox with excess index rows.
    # The resource guard must run before the expensive integrity audit.
    with state._write() as db:
        batch = db.execute(
            "SELECT batch_sha256 FROM static_adapter_designs"
        ).fetchone()[0]
        db.executemany(
            "INSERT INTO static_adapter_request_ids(request_id,batch_sha256) VALUES (?,?)",
            [(f"synthetic_extra_{i}", batch) for i in range(10000)],
        )

    def forbidden_audit(_db):
        raise AssertionError("unbounded audit must not run")

    monkeypatch.setattr(inventory, "_audit", forbidden_audit)
    with pytest.raises(ValueError, match="exceeds continuity limit"):
        inventory.snapshot_static_design_records(state)


def test_snapshot_still_audits_small_corrupt_index(tmp_path):
    state = DurableResearchState(tmp_path / "synthetic.sqlite3")
    name, spec = next(iter(REGISTRY.items()))
    stage_static_adapter_designs(state, [{
        "schema": SCHEMA, "adapter": name, "request_id": "synthetic_seed",
        "payload_schema": spec.inputs[0],
        "payload": {"field_names": ["synthetic_column"]},
    }])
    with state._write() as db:
        db.execute("DELETE FROM static_adapter_request_ids")
    with pytest.raises(ValueError):
        inventory.snapshot_static_design_records(state)


def test_snapshot_rejects_orphan_request_table_before_count(tmp_path):
    state = DurableResearchState(tmp_path / "synthetic.sqlite3")
    # A partial synthetic schema must be rejected before any COUNT query.
    with state._write() as db:
        db.execute("CREATE TABLE static_adapter_request_ids (request_id TEXT)")
    with pytest.raises(ValueError, match="Incomplete static design inbox schema"):
        inventory.snapshot_static_design_records(state)
