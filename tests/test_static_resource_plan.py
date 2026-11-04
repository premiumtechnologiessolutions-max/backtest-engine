"""Synthetic DAG wave scheduling. Never starts a worker or reads quotes."""
import copy

import pytest

from norisk_quant.campaign_blueprint import freeze_blueprint
from norisk_quant.static_resource_plan import (
    plan_resource_waves, verify_resource_waves,
)


def blueprint(max_workers=2, ram=4096, disk=2048, runtime=120):
    spec = {
        "source_commit": "a" * 40,
        "dataset": {"id": "xauusd_m1", "archive_sha256": "b" * 64,
                    "start": "2020-01-01", "end": "2026-01-31",
                    "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2024-01-01", "end": "2024-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [
            {"id": name, "code_sha256": "c" * 64, "spec_sha256": "d" * 64}
            for name in ["bos_fib", "liquidity_sweep"]
        ],
        "execution_engines": ["norisk_quant", "lean", "nautilus"],
        "ai_reviewers": ["rd_agent", "tradingagents"],
        "resource_limits": {"max_workers": max_workers, "max_ram_mb": ram,
                            "max_disk_mb": disk, "max_runtime_minutes": runtime},
        "all_in_cost_usd_per_ounce": 0.40,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    }
    return freeze_blueprint(spec)


def test_all_nodes_planned_exactly_once_and_dependencies_precede_wave():
    frozen = blueprint()
    plan = plan_resource_waves(frozen)
    assert verify_resource_waves(frozen, plan) == plan
    seen = set()
    for wave in plan["waves"]:
        assert wave["execution_enabled"] is False
        assert len(wave["planned_nodes"]) <= 2
        assert wave["estimated_ram_mb"] <= 4096
        assert wave["estimated_scratch_mb"] <= 2048
        for name in wave["planned_nodes"]:
            node = next(n for n in frozen["dag"] if n["id"] == name)
            assert set(node["depends_on"]) <= seen
            assert name not in seen
        seen.update(wave["planned_nodes"])
    assert seen == {n["id"] for n in frozen["dag"]}
    assert plan["node_count"] == len(seen)
    assert plan["worker_started"] is False
    assert plan["market_data_accessed"] is False


def test_insufficient_ram_rejects_not_overcommits():
    with pytest.raises(ValueError, match="cannot fit ready stage"):
        plan_resource_waves(blueprint(ram=256))


def test_single_worker_produces_more_waves_than_two():
    one = plan_resource_waves(blueprint(max_workers=1))
    two = plan_resource_waves(blueprint(max_workers=2))
    assert one["wave_count"] >= two["wave_count"]
    assert one["node_count"] == two["node_count"]


def test_heuristic_overbudget_is_marked_not_executed():
    result = plan_resource_waves(blueprint(runtime=40))
    assert result["requires_resource_replanning"] is True
    assert result["within_declared_runtime_budget"] is False
    assert result["planning_is_not_runtime_benchmark"] is True
    assert result["status"] == "STATIC_CAPACITY_DESIGN_NOT_EXECUTED"


def test_plan_tampering_or_foreign_blueprint_rejected():
    frozen = blueprint()
    plan = plan_resource_waves(frozen)
    fake = copy.deepcopy(plan)
    fake["waves"][0]["execution_enabled"] = True
    with pytest.raises(ValueError):
        verify_resource_waves(frozen, fake)
    foreign = blueprint(max_workers=1)
    with pytest.raises(ValueError):
        verify_resource_waves(foreign, plan)


def test_large_synthetic_strategy_fanout_is_bounded_without_running():
    spec = blueprint()["normalized_spec"]
    spec["strategies"] = [
        {"id": f"strat_{i:02d}", "code_sha256": "c" * 64,
         "spec_sha256": "d" * 64} for i in range(20)]
    spec["ai_reviewers"] = []
    frozen = freeze_blueprint(spec)
    planned = plan_resource_waves(frozen)
    assert planned["node_count"] == 2 + 20 * (1 + 3 + 1 + 1) + 1
    assert planned["result_accepted"] is False
