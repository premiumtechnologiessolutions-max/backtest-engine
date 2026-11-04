"""Sharded construction-only campaign planner for thousands of frozen strategies.

Splits bounded hypothesis universes into deterministic subgraphs, then applies
the INERT static resource planner to each subgraph. Does not run anything.
"""
from __future__ import annotations

import hashlib
import json
import re

from norisk_quant.campaign_blueprint import freeze_blueprint, verify_blueprint
from norisk_quant.static_resource_plan import (
    plan_resource_waves, verify_resource_waves,
)

SCHEMA = "NRFX_QUANT_SHARDED_CAMPAIGN_DESIGN_V1"
_MAX_STRATEGIES = 4096
_NAME = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")).hexdigest()


def freeze_sharded_campaign(spec: dict) -> dict:
    """Compile an immutable, bounded, reproducible engineering design.

    Per-shard fanout is capped so a run's DAG cannot explode beyond known
    construction memory budgets. A *future* orchestrator must handle global
    multiple-testing correction over ALL hypotheses, not each shard alone.
    """
    if type(spec) is not dict:
        raise ValueError("Expected exact frozen campaign object")
    candidates = spec.get("strategies")
    if type(candidates) is not list or not 1 <= len(candidates) <= _MAX_STRATEGIES:
        raise ValueError("Sharded campaign requires 1..4096 strategies")
    validated_names = set()
    for item in candidates:
        if (type(item) is not dict
                or set(item) != {"id", "code_sha256", "spec_sha256"}
                or type(item["id"]) is not str
                or not _NAME.fullmatch(item["id"])
                or item["id"] in validated_names
                or any(type(item[k]) is not str or not _SHA.fullmatch(item[k])
                       for k in ("code_sha256", "spec_sha256"))):
            raise ValueError("Duplicate, unsafe or unfrozen strategy in global universe")
        validated_names.add(item["id"])
    ordered = sorted(candidates, key=lambda c: c["id"])
    # Validate every shared policy (source, fees, owner freeze, resources,
    # provider allowlists) through the already reviewed small-DAG compiler.
    first = dict(spec, strategies=ordered[:1])
    seed = freeze_blueprint(first)
    normalized = dict(seed["normalized_spec"], strategies=ordered)
    engines = len(normalized["execution_engines"])
    reviewers = len(normalized["ai_reviewers"])
    fanout = engines + reviewers
    chunk_size = min(32, max(1, 150 // fanout))
    shards = []
    for i, offset in enumerate(range(0, len(ordered), chunk_size), 1):
        chunk = ordered[offset:offset + chunk_size]
        shared = dict(normalized, strategies=chunk)
        frozen = freeze_blueprint(shared)
        planned = plan_resource_waves(frozen)
        shards.append({
            "shard_index": i,
            "strategy_ids": [entry["id"] for entry in chunk],
            "blueprint": frozen,
            "resource_plan": planned,
            "status": "DESIGN_NOT_EXECUTED",
        })
    body = {
        "schema": SCHEMA,
        "normalized_global_spec": normalized,
        "global_spec_sha256": _digest(normalized),
        "frozen_shards": shards,
        "strategy_count": len(ordered),
        "shard_count": len(shards),
        "total_designed_nodes": sum(s["blueprint"]["node_count"] for s in shards),
        "sum_of_sequential_static_wall_estimates_minutes": sum(
            s["resource_plan"]["estimated_wall_minutes"] for s in shards),
        "strategy_universe_is_global_across_shards": True,
        "cross_shard_multiple_testing_control_implemented": False,
        "status": "SHARDED_ENGINEERING_BLUEPRINT_ONLY",
        "workers_started": False,
        "source_data_accessed": False,
        "research_results_accepted": False,
        "live_trading_authorized": False,
    }
    return {**body, "sharded_blueprint_sha256": _digest(body)}


def verify_sharded_campaign(candidate: object) -> dict:
    if type(candidate) is not dict or "normalized_global_spec" not in candidate:
        raise ValueError("Missing sharded research blueprint")
    rebuilt = freeze_sharded_campaign(candidate["normalized_global_spec"])
    if candidate != rebuilt:
        raise ValueError("Modified or misleading campaign shard design")
    return rebuilt
