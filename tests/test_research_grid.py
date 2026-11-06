"""Synthetic, zero-market-execution tests for research grid planning."""
import hashlib
import json

import pytest
from scripts import research_grid as rg
from scripts.research_batch import ResearchBatchError


def grid(tmp_path):
    return {
        "schema": "NRFX_GRID_V1",
        "source": str(tmp_path / "data.zip"),
        "source_sha256": "b" * 64,
        "engine_commit": "a" * 40,
        "start": "2012-01-01", "end": "2013-12-31",
        "grids": [{
            "id_prefix": "emaM15", "strategy": "ema",
            "timeframe": "M15", "execution": "fast",
            "axes": {
                "fast": [5, 30], "slow": [21, 50],
                "stop_atr": [1.0, 1.5], "rr": [1.0, 2.0],
            },
        }],
    }


def test_deterministic_grid_and_explicit_invalid_skips(tmp_path):
    obj = grid(tmp_path)
    specs, audit = rg.expand_grid(obj)
    assert audit["raw_combinations"] == 16
    assert audit["rejected"] == 4
    assert audit["accepted"] == 12
    assert [s["id"] for s in specs] == [s["id"] for s in rg.expand_grid(obj)[0]]
    assert all(s["parameters"]["fast"] < s["parameters"]["slow"] for s in specs)


def test_offline_shards_record_hash_and_no_replay(tmp_path):
    out = tmp_path / "plans"
    result = rg.write_shards(grid(tmp_path), out)
    assert result["status"] == "FROZEN_PLANS_ONLY_NO_BACKTEST_EXECUTED"
    assert len(result["shards"]) == 1
    row = result["shards"][0]
    contents = (out / row["file"]).read_bytes()
    assert hashlib.sha256(contents).hexdigest() == row["sha256"]
    assert len(json.loads(contents)["experiments"]) == 12


def test_sharding_at_50_candidates(tmp_path):
    obj = grid(tmp_path)
    obj["grids"][0]["axes"]["rr"] = [round(1 + .1*i, 2) for i in range(12)]
    obj["grids"][0]["axes"]["slow"] = [31, 51]
    result = rg.write_shards(obj, tmp_path / "many")
    assert result["grid_stats"]["accepted"] == 96
    assert [part["experiments"] for part in result["shards"]] == [50, 46]


def test_invalid_duplicate_axis_fails(tmp_path):
    obj = grid(tmp_path)
    obj["grids"][0]["axes"]["fast"] = [5, 5]
    with pytest.raises(ResearchBatchError, match="Duplicate"):
        rg.expand_grid(obj)


def test_bound_limits_candidate_explosion(tmp_path):
    obj = grid(tmp_path)
    for k in obj["grids"][0]["axes"]:
        obj["grids"][0]["axes"][k] = list(range(1, 101))
    with pytest.raises(ResearchBatchError):
        rg.expand_grid(obj)


def test_invalid_boolean_parameter_must_not_be_ignored(tmp_path):
    obj = grid(tmp_path)
    obj["grids"][0]["axes"]["stop_atr"] = [1.0, True]
    with pytest.raises(ResearchBatchError):
        rg.expand_grid(obj)


def test_all_invalid_settings_fail(tmp_path):
    obj = grid(tmp_path)
    obj["grids"][0]["axes"]["fast"] = [50]
    obj["grids"][0]["axes"]["slow"] = [21]
    with pytest.raises(ResearchBatchError, match="No valid"):
        rg.expand_grid(obj)


def test_overwrite_guard(tmp_path):
    out = tmp_path / "existing"
    out.mkdir()
    (out / "important").write_text("keep")
    with pytest.raises(ResearchBatchError, match="already exists"):
        rg.write_shards(grid(tmp_path), out)
    assert (out / "important").read_text() == "keep"


def test_duplicate_configurations_across_groups_rejected(tmp_path):
    obj = grid(tmp_path)
    duplicate = {**obj["grids"][0], "id_prefix": "other"}
    obj["grids"].append(duplicate)
    with pytest.raises(ResearchBatchError, match="Duplicate configuration"):
        rg.expand_grid(obj)
