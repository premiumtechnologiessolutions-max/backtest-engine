"""Synthetic-only regression tests for the inert design inventory."""
import hashlib
import json

import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_static_adapter_designs import stage_static_adapter_designs
from scripts.static_design_inventory import inspect_static_design_inventory
from scripts.static_adapter_envelope import SCHEMA
from scripts.static_external_adapter_registry import REGISTRY


def _batch(prefix):
    name, spec = next(iter(REGISTRY.items()))
    return [{
        "schema": SCHEMA, "adapter": name, "request_id": prefix,
        "payload_schema": spec.inputs[0],
        "payload": {"field_names": ["synthetic_column"]},
    }]


def test_empty_inventory_is_read_only_and_deterministic(tmp_path):
    state = DurableResearchState(tmp_path / "state.sqlite3")
    first = inspect_static_design_inventory(state)
    assert first == inspect_static_design_inventory(state)
    assert first["batches"] == first["requests"] == first["jobs_created"] == 0
    assert first["inventory_sha256"] == hashlib.sha256(b"[]").hexdigest()
    assert first["execution_authorized"] is False
    with state._connection() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE name='static_adapter_designs'"
        ).fetchone()[0] == 0


def test_staged_designs_have_stable_order_independent_fingerprint(tmp_path):
    state = DurableResearchState(tmp_path / "state.sqlite3")
    a = stage_static_adapter_designs(state, _batch("synthetic_a"))
    b = stage_static_adapter_designs(state, _batch("synthetic_b"))
    observed = inspect_static_design_inventory(state)
    expected = json.dumps(sorted([a["batch_sha256"], b["batch_sha256"]]),
                          separators=(",", ":")).encode("ascii")
    assert observed["inventory_sha256"] == hashlib.sha256(expected).hexdigest()
    assert observed["batches"] == 2 and observed["requests"] == 2
    assert observed["jobs_created"] == 0
    assert observed["results_verified"] is False
    assert observed == inspect_static_design_inventory(state)
    with state._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_corrupt_manifest_never_produces_inventory_receipt(tmp_path):
    state = DurableResearchState(tmp_path / "state.sqlite3")
    stage_static_adapter_designs(state, _batch("synthetic_a"))
    with state._write() as db:
        db.execute("UPDATE static_adapter_designs SET manifest_json='{}'")
    with pytest.raises(ValueError):
        inspect_static_design_inventory(state)


def test_missing_index_table_fails_closed(tmp_path):
    state = DurableResearchState(tmp_path / "state.sqlite3")
    stage_static_adapter_designs(state, _batch("synthetic_a"))
    with state._write() as db:
        db.execute("DROP TABLE static_adapter_request_ids")
    with pytest.raises(ValueError, match="Incomplete"):
        inspect_static_design_inventory(state)


def test_invalid_state_rejected(tmp_path):
    with pytest.raises(ValueError, match="Expected durable"):
        inspect_static_design_inventory(None)


def test_summary_refuses_oversized_index_before_audit(tmp_path, monkeypatch):
    from scripts import static_design_inventory as inventory
    state = DurableResearchState(tmp_path / "synthetic.sqlite3")
    stage_static_adapter_designs(state, _batch("synthetic_seed"))
    with state._write() as db:
        batch = db.execute("SELECT batch_sha256 FROM static_adapter_designs").fetchone()[0]
        db.executemany(
            "INSERT INTO static_adapter_request_ids(request_id,batch_sha256) VALUES (?,?)",
            [(f"synthetic_extra_{i}", batch) for i in range(10000)],
        )
    monkeypatch.setattr(inventory, "_audit", lambda _: (_ for _ in ()).throw(
        AssertionError("unbounded audit executed")))
    with pytest.raises(ValueError, match="exceeds continuity limit"):
        inventory.inspect_static_design_inventory(state)


def test_summary_refuses_orphan_request_table_before_audit(tmp_path):
    state = DurableResearchState(tmp_path / "synthetic.sqlite3")
    with state._write() as db:
        db.execute("CREATE TABLE static_adapter_request_ids (request_id TEXT)")
    with pytest.raises(ValueError, match="Incomplete static design inbox schema"):
        inspect_static_design_inventory(state)
