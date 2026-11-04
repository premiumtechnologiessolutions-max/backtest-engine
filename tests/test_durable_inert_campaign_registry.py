"""Atomic inert research DAG registry tests, synthetic campaign metadata only."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_inert_campaign_registry import (
    register_inert_campaign, audit_inert_campaign, audit_inert_registry,
)
from norisk_quant.campaign_sharding import freeze_sharded_campaign


def frozen(n=2):
    return freeze_sharded_campaign({
        "source_commit": "a" * 40,
        "dataset": {"id": "xauusd_m1", "archive_sha256": "b" * 64,
                    "start": "2010-01-01", "end": "2026-01-01",
                    "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2024-01-01", "end": "2024-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [
            {"id": f"strat_{i:03d}", "code_sha256": "c" * 64,
             "spec_sha256": "d" * 64} for i in range(n)],
        "execution_engines": ["norisk_quant", "lean"],
        "ai_reviewers": ["rd_agent"],
        "resource_limits": {"max_workers": 2, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 360},
        "all_in_cost_usd_per_ounce": 0.4,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    })


def test_register_entire_dag_and_audit_its_dependencies_without_running(tmp_path):
    store = DurableResearchState(tmp_path / "state.sqlite3")
    design = frozen()
    registered = register_inert_campaign(store, design)
    assert registered["registration_status"] == "REGISTERED_INERT"
    assert registered["node_count"] == design["total_designed_nodes"]
    assert registered["worker_started"] is False
    assert registered["research_results_accepted"] is False
    assert audit_inert_campaign(store, design["sharded_blueprint_sha256"])["node_count"] == registered["node_count"]
    assert audit_inert_registry(store)["planned_nodes"] == registered["node_count"]
    assert store.operational_snapshot(now_ms=1000)["total_jobs"] == 0


def test_repeated_registration_and_concurrency_are_idempotent(tmp_path):
    store = DurableResearchState(tmp_path / "state.sqlite3")
    design = frozen()
    with ThreadPoolExecutor(max_workers=4) as pool:
        replies = list(pool.map(lambda _: register_inert_campaign(store, design), range(7)))
    assert sum(r["registration_status"] == "REGISTERED_INERT" for r in replies) == 1
    assert sum(r["registration_status"] == "ALREADY_REGISTERED_IDENTICAL" for r in replies) == 6
    with store._connection() as db:
        assert db.execute("SELECT COUNT(*) FROM construction_campaigns").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM construction_nodes").fetchone()[0] == design["total_designed_nodes"]


def test_mutated_node_or_deleted_dependency_cannot_pass_audit(tmp_path):
    store = DurableResearchState(tmp_path / "state.sqlite3")
    design = frozen()
    register_inert_campaign(store, design)
    sha = design["sharded_blueprint_sha256"]
    with store._write() as db:
        db.execute("UPDATE construction_nodes SET node_json='{}' "
                   "WHERE campaign_sha=? AND node_id=(SELECT MIN(node_id) "
                   "FROM construction_nodes WHERE campaign_sha=?)", (sha,sha))
    with pytest.raises(ValueError, match="differs"):
        audit_inert_campaign(store, sha)


def test_removed_node_is_detected_and_cannot_be_silently_rebuilt(tmp_path):
    store = DurableResearchState(tmp_path / "state.sqlite3")
    design = frozen()
    register_inert_campaign(store, design)
    sha = design["sharded_blueprint_sha256"]
    with store._write() as db:
        db.execute("DELETE FROM construction_nodes WHERE campaign_sha=? "
                   "AND node_id=(SELECT MIN(node_id) FROM construction_nodes "
                   "WHERE campaign_sha=?)", (sha, sha))
    with pytest.raises(ValueError, match="differs"):
        register_inert_campaign(store, design)
    with pytest.raises(ValueError, match="differs"):
        audit_inert_registry(store)


def test_wrong_or_modified_frozen_design_never_registered(tmp_path):
    store = DurableResearchState(tmp_path / "state.sqlite3")
    bad = frozen()
    bad["frozen_shards"][0]["blueprint"]["dag"][0]["execution_enabled"] = True
    with pytest.raises(ValueError):
        register_inert_campaign(store, bad)
    assert audit_inert_registry(store)["campaign_count"] == 0


def test_two_shards_have_namespaced_independent_dependency_ids(tmp_path):
    store = DurableResearchState(tmp_path / "state.sqlite3")
    design = frozen(45)
    result = register_inert_campaign(store, design)
    assert result["shard_count"] > 1
    with store._connection() as db:
        rows = db.execute("SELECT node_id FROM construction_nodes").fetchall()
        assert len(rows) == len({r[0] for r in rows})
        assert any(r[0].startswith("0002/") for r in rows)
    assert audit_inert_registry(store)["execution_enabled"] is False
