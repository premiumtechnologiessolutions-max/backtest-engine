"""Large-universe synthetic planning only; no actual strategies or workers."""
import copy

import pytest

from norisk_quant.campaign_sharding import (
    freeze_sharded_campaign, verify_sharded_campaign,
)


def spec(count, *, engines=None, reviewers=None):
    return {
        "source_commit": "a" * 40,
        "dataset": {
            "id": "xauusd_m1", "archive_sha256": "b" * 64,
            "start": "2010-01-01", "end": "2026-01-01",
            "format": "M1_BID_ASK_ORIGINAL",
        },
        "evaluation": {
            "start": "2024-01-01", "end": "2024-12-31",
            "scope": "UNEXECUTED_RESEARCH_DESIGN",
        },
        "strategies": [
            {"id": f"hypothesis_{i:05d}",
             "code_sha256": "c" * 64,
             "spec_sha256": "d" * 64}
            for i in range(count)
        ],
        "execution_engines": (
            engines if engines is not None
            else ["lean", "nautilus", "norisk_quant"]),
        "ai_reviewers": (
            reviewers if reviewers is not None
            else ["rd_agent", "tradingagents", "finrl"]),
        "resource_limits": {
            "max_workers": 2, "max_ram_mb": 4096,
            "max_disk_mb": 2048, "max_runtime_minutes": 1440,
        },
        "all_in_cost_usd_per_ounce": 0.40,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    }


def test_257_strategies_are_completely_sharded_without_work():
    design = freeze_sharded_campaign(spec(257))
    assert design["strategy_count"] == 257
    assert design["shard_count"] == 11  # six reviewers/engines => 25 per shard
    assert all(1 <= len(s["strategy_ids"]) <= 25
               for s in design["frozen_shards"])
    assert design["total_designed_nodes"] > 257
    assert design["workers_started"] is False
    assert design["source_data_accessed"] is False
    assert design["research_results_accepted"] is False
    ids = [identifier
           for shard in design["frozen_shards"]
           for identifier in shard["strategy_ids"]]
    assert len(ids) == len(set(ids)) == 257
    assert verify_sharded_campaign(design) == design


def test_1025_synthetic_hypotheses_have_fixed_fingerprints():
    frozen = freeze_sharded_campaign(spec(1025, engines=["norisk_quant"],
                                          reviewers=[]))
    assert frozen["strategy_count"] == 1025
    assert frozen["shard_count"] == 33
    assert frozen["status"] == "SHARDED_ENGINEERING_BLUEPRINT_ONLY"


def test_shuffling_input_does_not_modify_frozen_campaign():
    left = spec(34)
    right = copy.deepcopy(left)
    right["strategies"].reverse()
    right["execution_engines"].reverse()
    right["ai_reviewers"].reverse()
    assert freeze_sharded_campaign(left) == freeze_sharded_campaign(right)


@pytest.mark.parametrize("count", [0, 4097])
def test_unbounded_or_empty_global_universe_fails(count):
    with pytest.raises(ValueError):
        freeze_sharded_campaign(spec(count))


def test_duplicates_and_illegal_external_authority_rejected():
    x = spec(3)
    x["strategies"].append(dict(x["strategies"][0]))
    with pytest.raises(ValueError):
        freeze_sharded_campaign(x)
    x = spec(3)
    x["owner_policy"] = "ALLOW_REAL_BACKTEST"
    with pytest.raises(ValueError):
        freeze_sharded_campaign(x)
    x = spec(3)
    x["credentials"] = "SECRET"
    with pytest.raises(ValueError):
        freeze_sharded_campaign(x)


def test_global_multiple_testing_is_not_pretended_to_be_per_shard():
    campaign = freeze_sharded_campaign(spec(90))
    assert campaign["strategy_universe_is_global_across_shards"] is True
    assert campaign["cross_shard_multiple_testing_control_implemented"] is False
    assert campaign["live_trading_authorized"] is False


def test_tampering_any_nested_shard_is_rejected():
    blueprint = freeze_sharded_campaign(spec(50))
    altered = copy.deepcopy(blueprint)
    altered["frozen_shards"][0]["resource_plan"]["workers_started"] = True
    with pytest.raises(ValueError):
        verify_sharded_campaign(altered)
