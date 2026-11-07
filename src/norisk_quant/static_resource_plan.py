"""Deterministic resource-wave planning for the INERT quant campaign DAG.

The planner never invokes execution stages, workers, OpenBB, submodules,
market data or strategy evaluation. Cost/time profiles are unmeasured
conservative placeholders, not observed performance or runnable commands.
"""
from __future__ import annotations

import hashlib
import json

from norisk_quant.campaign_blueprint import verify_blueprint

SCHEMA = "NRFX_QUANT_STATIC_RESOURCE_PLAN_V1"

# Stage estimates exist to reveal impossible declared capacity, not benchmark.
_STAGE_PROFILE = {
    "source_integrity": (256, 256, 5),
    "causal_alignment": (512, 512, 10),
    "strategy_compilation": (256, 128, 3),
    "reference_simulation": (1024, 512, 30),
    "execution_reconciliation": (256, 128, 5),
    "portfolio_risk": (512, 256, 5),
    "failure_review": (512, 256, 15),
    "report_assembly": (256, 128, 10),
}


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True, allow_nan=False).encode("ascii")
    ).hexdigest()


def plan_resource_waves(blueprint: dict) -> dict:
    """Assign a reproducible topological sequence of NONEXECUTABLE waves.

    Greedy scheduling chooses by frozen DAG node order; dependencies may only
    be satisfied by an EARLIER wave, never by peer tasks in the same wave.
    RAM and scratch disk estimates sum within each wave, duration is the
    maximum stage estimate. No service is launched by this function.
    """
    frozen = verify_blueprint(blueprint)
    policy = frozen["normalized_spec"]["resource_limits"]
    tasks = frozen["dag"]
    remaining = {node["id"]: node for node in tasks}
    completed = set()
    waves = []
    while remaining:
        ready = [
            node for node in tasks
            if node["id"] in remaining
            and all(dep in completed for dep in node["depends_on"])
        ]
        if not ready:
            raise ValueError("Frozen research dependency graph cannot progress")
        accepted = []
        ram = disk = max_minutes = 0
        for node in ready:
            profile = _STAGE_PROFILE[node["stage"]]
            request_ram, request_disk, minutes = profile
            if (len(accepted) < policy["max_workers"]
                    and ram + request_ram <= policy["max_ram_mb"]
                    and disk + request_disk <= policy["max_disk_mb"]):
                accepted.append(node["id"])
                ram += request_ram
                disk += request_disk
                max_minutes = max(max_minutes, minutes)
        if not accepted:
            raise ValueError("Declared resource budget cannot fit ready stage")
        waves.append({
            "wave": len(waves) + 1,
            "planned_nodes": accepted,
            "estimated_ram_mb": ram,
            "estimated_scratch_mb": disk,
            "estimated_minutes": max_minutes,
            "execution_enabled": False,
        })
        # These are DESIGN dependencies, never completed research tasks.
        completed.update(accepted)
        for name in accepted:
            del remaining[name]
    estimated_wall = sum(w["estimated_minutes"] for w in waves)
    plan = {
        "schema": SCHEMA,
        "blueprint_sha256": frozen["blueprint_sha256"],
        "resource_limits": policy,
        "cost_profile": "STATIC_UNMEASURED_HEURISTIC_V1",
        "waves": waves,
        "node_count": len(tasks),
        "wave_count": len(waves),
        "estimated_wall_minutes": estimated_wall,
        "within_declared_runtime_budget": (
            estimated_wall <= policy["max_runtime_minutes"]),
        "requires_resource_replanning": (
            estimated_wall > policy["max_runtime_minutes"]),
        "status": "STATIC_CAPACITY_DESIGN_NOT_EXECUTED",
        "planning_is_not_runtime_benchmark": True,
        "worker_started": False,
        "providers_invoked": False,
        "market_data_accessed": False,
        "result_accepted": False,
    }
    return {**plan, "plan_sha256": _digest(plan)}


def verify_resource_waves(blueprint: dict, plan: object) -> dict:
    if type(plan) is not dict or plan != plan_resource_waves(blueprint):
        raise ValueError("Modified or mismatched static quant resource plan")
    return plan
