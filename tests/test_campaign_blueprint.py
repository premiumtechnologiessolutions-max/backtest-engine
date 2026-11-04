"""Synthetic DAG construction tests: no source reads or market jobs."""
import copy
import json

import pytest

from norisk_quant.campaign_blueprint import freeze_blueprint, verify_blueprint


def sample():
    return {
        "source_commit": "a" * 40,
        "dataset": {"id": "xauusd_m1", "archive_sha256": "b" * 64,
                    "start": "2010-01-01", "end": "2026-10-31",
                    "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2024-01-01", "end": "2024-12-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [
            {"id": "liquidity_sweep", "code_sha256": "c" * 64,
             "spec_sha256": "d" * 64},
            {"id": "bos_fib", "code_sha256": "e" * 64,
             "spec_sha256": "f" * 64},
        ],
        "execution_engines": ["nautilus", "norisk_quant", "lean"],
        "ai_reviewers": ["tradingagents", "rd_agent"],
        "resource_limits": {"max_workers": 2, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.40,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    }


def test_compiles_full_quant_pipeline_without_executing():
    graph = freeze_blueprint(sample())
    assert verify_blueprint(graph) == graph
    assert graph["node_count"] == 2 + 2 * (1 + 3 + 1 + 1 + 2) + 1
    ids = {n["id"]: n for n in graph["dag"]}
    assert ids["reconcile__bos_fib"]["depends_on"] == [
        "simulate__bos_fib__lean",
        "simulate__bos_fib__nautilus",
        "simulate__bos_fib__norisk_quant",
    ]
    assert ids["review__bos_fib__rd_agent"]["depends_on"] == ["risk__bos_fib"]
    assert ids["assemble_report"]["depends_on"]
    assert all(n["execution_enabled"] is False and n["result_accepted"] is False
               for n in graph["dag"])
    assert graph["provider_invoked"] is False
    assert graph["market_data_accessed"] is False
    assert graph["strategy_backtested"] is False
    assert graph["live_trading_authorized"] is False


def test_fingerprint_deterministic_across_strategy_provider_order():
    first = sample()
    other = copy.deepcopy(first)
    other["strategies"].reverse()
    other["execution_engines"].reverse()
    other["ai_reviewers"].reverse()
    assert freeze_blueprint(first) == freeze_blueprint(other)


@pytest.mark.parametrize("field,change", [
    ("owner_policy", "RUN_MARKET_RESEARCH"),
    ("all_in_cost_usd_per_ounce", 0.5),
    ("all_in_cost_usd_per_ounce", True),
    ("source_commit", "not-a-commit"),
])
def test_rejects_unsafe_source_cost_or_run_authority(field, change):
    spec = sample()
    spec[field] = change
    with pytest.raises(ValueError):
        freeze_blueprint(spec)


def test_rejects_unbounded_resource_limits_and_unknown_provider():
    x = sample()
    x["resource_limits"]["max_workers"] = 200
    with pytest.raises(ValueError):
        freeze_blueprint(x)
    x = sample()
    x["execution_engines"].append("openbb")
    with pytest.raises(ValueError):
        freeze_blueprint(x)
    x = sample()
    x["execution_engines"] = ["lean"]
    with pytest.raises(ValueError, match="reference engine"):
        freeze_blueprint(x)


def test_rejects_duplicate_ids_or_nonfinite_and_extra_credentials():
    x = sample()
    x["strategies"].append(copy.deepcopy(x["strategies"][0]))
    with pytest.raises(ValueError):
        freeze_blueprint(x)
    x = sample()
    x["credentials"] = "BROKER_TOKEN"
    with pytest.raises(ValueError, match="schema"):
        freeze_blueprint(x)
    x = sample()
    x["dataset"]["api_key"] = "secret"
    with pytest.raises(ValueError):
        freeze_blueprint(x)


def test_rejects_historical_window_outside_frozen_data():
    x = sample()
    x["evaluation"]["end"] = "2028-01-01"
    with pytest.raises(ValueError):
        freeze_blueprint(x)
    x = sample()
    x["evaluation"]["start"] = "2024-02-31"
    with pytest.raises(ValueError):
        freeze_blueprint(x)


def test_rejects_mutated_graph_even_if_self_rehashed():
    blueprint = freeze_blueprint(sample())
    tampered = copy.deepcopy(blueprint)
    tampered["dag"][0]["execution_enabled"] = True
    with pytest.raises(ValueError):
        verify_blueprint(tampered)
    tampered = copy.deepcopy(blueprint)
    tampered["node_count"] = 0
    with pytest.raises(ValueError):
        verify_blueprint(tampered)
    tampered = copy.deepcopy(blueprint)
    tampered["status"] = "DONE"
    with pytest.raises(ValueError):
        verify_blueprint(tampered)


def test_json_round_trip_and_minimal_reference_only():
    frozen = freeze_blueprint(sample())
    restored = json.loads(json.dumps(frozen))
    assert verify_blueprint(restored) == frozen
    assert "prices" not in json.dumps(frozen).lower()
    assert "broker_token" not in json.dumps(frozen).lower()


def test_empty_ai_reviewers_still_builds_core():
    x = sample()
    x["ai_reviewers"] = []
    x["execution_engines"] = ["norisk_quant"]
    graph = freeze_blueprint(x)
    assert graph["node_count"] == 2 + 2 * (1 + 1 + 1 + 1) + 1
    assert all(not n["id"].startswith("review__") for n in graph["dag"])
