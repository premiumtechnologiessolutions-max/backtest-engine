"""Synthetic-only SQLite snapshot concurrency invariants.

No market data, research jobs, vendor engines or workers are started.
"""
import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_static_adapter_designs import stage_static_adapter_designs
from scripts.static_adapter_envelope import SCHEMA
from scripts.static_external_adapter_registry import REGISTRY
import scripts.static_design_inventory as inventory


def _envelope(request_id):
    adapter, spec = next(iter(REGISTRY.items()))
    return [{"schema": SCHEMA, "adapter": adapter, "request_id": request_id,
             "payload_schema": spec.inputs[0],
             "payload": {"field_names": ["synthetic_column"]}}]


@pytest.mark.parametrize("reader", [
    inventory.inspect_static_design_inventory,
    inventory.snapshot_static_design_records,
])
def test_reader_uses_one_sqlite_snapshot_across_audit_and_rows(tmp_path, monkeypatch, reader):
    """A concurrent committed append must not appear halfway through a read."""
    state = DurableResearchState(tmp_path / "synthetic.sqlite3")
    stage_static_adapter_designs(state, _envelope("synthetic_before"))
    original_audit = inventory._audit
    appended = []

    def audit_then_append(db):
        summary = original_audit(db)
        # WAL permits a second connection to commit while the reader holds
        # its earlier snapshot. If not WAL, the test explicitly skips.
        with state._connection() as probe:
            mode = probe.execute("PRAGMA journal_mode").fetchone()[0]
        if mode.lower() != "wal":
            pytest.skip("Concurrent writer requires WAL mode")
        stage_static_adapter_designs(state, _envelope("synthetic_after"))
        appended.append(True)
        return summary

    monkeypatch.setattr(inventory, "_audit", audit_then_append)
    result = reader(state)
    assert appended == [True]
    if reader is inventory.inspect_static_design_inventory:
        assert result["requests"] == 1
    else:
        assert len(result) == 1
        assert result[0]["request_id"] == "synthetic_before"

    monkeypatch.setattr(inventory, "_audit", original_audit)
    next_result = reader(state)
    if reader is inventory.inspect_static_design_inventory:
        assert next_result["requests"] == 2
    else:
        assert {row["request_id"] for row in next_result} == {
            "synthetic_before", "synthetic_after"
        }
