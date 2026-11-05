"""Synthetic-only durable adapter designs: no research jobs or engines."""
import copy
import sqlite3

import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_static_adapter_designs import (
    audit_static_adapter_designs, stage_static_adapter_designs,
)
from scripts.static_adapter_envelope import SCHEMA
from scripts.static_external_adapter_registry import REGISTRY


def batch(prefix="synthetic"):
    name, spec = next(iter(REGISTRY.items()))
    return [
        {"schema": SCHEMA, "adapter": name,
         "request_id": f"{prefix}_{n}", "payload_schema": spec.inputs[0],
         "payload": {"field_names": [f"column_{n}"]}}
        for n in (1, 2)
    ]


def store(tmp_path):
    return DurableResearchState(tmp_path / "state.sqlite3")


def test_stage_is_immutable_and_idempotent(tmp_path):
    state = store(tmp_path)
    envelopes = batch()
    original = copy.deepcopy(envelopes)
    first = stage_static_adapter_designs(state, envelopes)
    again = stage_static_adapter_designs(state, envelopes)
    assert first["status"] == "STAGED_DESIGN_ONLY"
    assert again["status"] == "ALREADY_STAGED_DESIGN_ONLY"
    assert first["batch_sha256"] == again["batch_sha256"]
    assert audit_static_adapter_designs(state)["requests"] == 2
    assert envelopes == original
    assert first["execution_authorized"] is False
    assert first["jobs_created"] == 0
    with state._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_cross_batch_duplicate_id_refused_without_partial_write(tmp_path):
    state = store(tmp_path)
    stage_static_adapter_designs(state, batch())
    changed = batch("different")
    changed[1]["request_id"] = "synthetic_1"
    with pytest.raises(ValueError, match="already belongs"):
        stage_static_adapter_designs(state, changed)
    assert audit_static_adapter_designs(state)["batches"] == 1
    assert audit_static_adapter_designs(state)["requests"] == 2


def test_corrupt_manifest_rejected_on_read_and_next_write(tmp_path):
    state = store(tmp_path)
    stage_static_adapter_designs(state, batch())
    with state._write() as db:
        db.execute("UPDATE static_adapter_designs SET manifest_json='{}'")
    with pytest.raises(ValueError, match="Corrupt"):
        audit_static_adapter_designs(state)
    with pytest.raises(ValueError, match="Corrupt"):
        stage_static_adapter_designs(state, batch("new"))


def test_missing_request_index_detected(tmp_path):
    state = store(tmp_path)
    stage_static_adapter_designs(state, batch())
    with state._write() as db:
        db.execute("DELETE FROM static_adapter_request_ids WHERE request_id='synthetic_1'")
    with pytest.raises(ValueError, match="index"):
        audit_static_adapter_designs(state)


def test_injected_permission_or_job_is_not_accepted(tmp_path):
    state = store(tmp_path)
    stage_static_adapter_designs(state, batch())
    with state._write() as db:
        db.execute("UPDATE static_adapter_designs SET state='DESIGN_ONLY_DISABLED' "
                   "WHERE state='DESIGN_ONLY_DISABLED'")
        db.execute("UPDATE static_adapter_designs SET envelopes_json='[]'")
    with pytest.raises(ValueError):
        audit_static_adapter_designs(state)


@pytest.mark.parametrize("invalid", [None, [], {}, [None]])
def test_invalid_batch_does_not_create_records(tmp_path, invalid):
    state = store(tmp_path)
    with pytest.raises(ValueError):
        stage_static_adapter_designs(state, invalid)
    assert audit_static_adapter_designs(state)["batches"] == 0


def test_empty_store_audit_does_not_create_design_tables(tmp_path):
    state = store(tmp_path)
    assert audit_static_adapter_designs(state)["requests"] == 0
    with state._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM sqlite_master "
                          "WHERE name='static_adapter_designs'").fetchone()[0] == 0


def test_reordered_batch_is_not_a_duplicate(tmp_path):
    state = store(tmp_path)
    original = batch()
    stage_static_adapter_designs(state, original)
    with pytest.raises(ValueError, match="already belongs"):
        stage_static_adapter_designs(state, list(reversed(original)))
    assert audit_static_adapter_designs(state)["batches"] == 1


def test_missing_index_table_fails_closed_without_recreating_it(tmp_path):
    state = store(tmp_path)
    stage_static_adapter_designs(state, batch())
    with state._write() as db:
        db.execute("DROP TABLE static_adapter_request_ids")
    with pytest.raises(ValueError, match="Incomplete static design tables"):
        audit_static_adapter_designs(state)
    with state._connection() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name='static_adapter_request_ids'"
        ).fetchone()[0] == 0


def test_empty_audit_does_not_create_index_or_design_tables(tmp_path):
    state = store(tmp_path)
    audit_static_adapter_designs(state)
    with state._connection() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND name IN ('static_adapter_designs','static_adapter_request_ids')"
        ).fetchone()[0] == 0


def test_index_table_only_is_corruption_not_empty_store(tmp_path):
    state = store(tmp_path)
    with state._write() as db:
        db.execute("CREATE TABLE static_adapter_request_ids ("
                   "request_id TEXT PRIMARY KEY, batch_sha256 TEXT NOT NULL)")
    with pytest.raises(ValueError, match="Incomplete static design tables"):
        audit_static_adapter_designs(state)


def test_recreated_index_table_without_foreign_key_is_refused(tmp_path):
    state = store(tmp_path)
    stage_static_adapter_designs(state, batch())
    with state._write() as db:
        db.execute("DROP TABLE static_adapter_request_ids")
        db.execute("CREATE TABLE static_adapter_request_ids ("
                   "request_id TEXT PRIMARY KEY, batch_sha256 TEXT NOT NULL)")
        db.executemany(
            "INSERT INTO static_adapter_request_ids VALUES (?,?)",
            [("synthetic_1", db.execute(
                "SELECT batch_sha256 FROM static_adapter_designs").fetchone()[0]),
             ("synthetic_2", db.execute(
                "SELECT batch_sha256 FROM static_adapter_designs").fetchone()[0])],
        )
    with pytest.raises(ValueError, match="foreign key"):
        audit_static_adapter_designs(state)
    with pytest.raises(ValueError, match="foreign key"):
        stage_static_adapter_designs(state, batch("another"))


def test_recreated_design_table_without_check_constraint_is_refused(tmp_path):
    state = store(tmp_path)
    with state._write() as db:
        db.execute("CREATE TABLE static_adapter_designs ("
                   "batch_sha256 TEXT PRIMARY KEY, manifest_json TEXT NOT NULL,"
                   "envelopes_json TEXT NOT NULL, state TEXT NOT NULL)")
        db.execute("CREATE TABLE static_adapter_request_ids ("
                   "request_id TEXT PRIMARY KEY, batch_sha256 TEXT NOT NULL "
                   "REFERENCES static_adapter_designs(batch_sha256))")
    with pytest.raises(ValueError, match="CHECK constraint"):
        audit_static_adapter_designs(state)


def test_missing_primary_key_is_refused_on_empty_schema(tmp_path):
    state = store(tmp_path)
    with state._write() as db:
        db.execute("CREATE TABLE static_adapter_designs ("
                   "batch_sha256 TEXT, manifest_json TEXT NOT NULL,"
                   "envelopes_json TEXT NOT NULL, state TEXT NOT NULL "
                   "CHECK(state='DESIGN_ONLY_DISABLED'))")
        db.execute("CREATE TABLE static_adapter_request_ids ("
                   "request_id TEXT PRIMARY KEY, batch_sha256 TEXT NOT NULL "
                   "REFERENCES static_adapter_designs(batch_sha256))")
    with pytest.raises(ValueError, match="schema drift"):
        audit_static_adapter_designs(state)
