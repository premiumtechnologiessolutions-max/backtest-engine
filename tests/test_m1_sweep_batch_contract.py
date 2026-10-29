"""Frozen batch registry contract for the M1-only sweep research hypothesis.

These tests define plans but never read private market data or claim backtest results.
"""
from pathlib import Path
import pytest
from scripts import research_batch_orchestrator as lab


def sweep_spec(*, timeframe="M1", parameters=None):
    return {
        "strategy": "m1-sweep", "timeframe": timeframe, "execution": "reference",
        "start": "2012-01-01", "end": "2012-12-31",
        "parameters": ({
            "sweep_lookback": 20, "sweep_min_excess_usd": .15,
            "sweep_reclaim_usd": .05, "sweep_stop_buffer_usd": .10,
            "sweep_reward_risk": 1.5, "sweep_max_stop_usd": 20.0,
        } if parameters is None else parameters),
    }


def frozen_plan(tmp_path):
    return {
        "schema": lab.SCHEMA, "dataset": str(tmp_path / "private.zip"),
        "source_sha256": "a" * 64, "engine_commit": "b" * 40,
        "exposure_context": "historical_exposed", "jobs": [],
        "grids": [{
            "strategy": "m1-sweep", "timeframe": "M1",
            "execution": "reference", "start": "2012-01-01",
            "end": "2012-12-31", "id_prefix": "m1swp",
            "grid": {"sweep_lookback": [10, 20],
                     "sweep_reward_risk": [1.0, 1.5, 2.0]},
        }],
    }


def test_frozen_sweep_spec_accepts_reference_and_fast_without_running_market():
    assert lab.check_spec(sweep_spec())["strategy"] == "m1-sweep"
    s = sweep_spec()
    s["execution"] = "fast"
    assert lab.check_spec(s)["execution"] == "fast"


@pytest.mark.parametrize("mutate", [
    {"timeframe": "M15"}, {"timeframe": "H1"},
    {"parameters": {"sweep_lookback": 2}},
    {"parameters": {"sweep_lookback": True}},
    {"parameters": {"sweep_lookback": 3.5}},
    {"parameters": {"sweep_min_excess_usd": -1.0}},
    {"parameters": {"sweep_reclaim_usd": float("nan")}},
    {"parameters": {"sweep_max_stop_usd": float("inf")}},
    {"parameters": {"sweep_stop_buffer_usd": 5.0,
                    "sweep_max_stop_usd": 1.0}},
    {"parameters": {"unsupported_parameter": 42}},
])
def test_frozen_factory_rejects_invalid_sweep(mutate):
    s = sweep_spec()
    s.update(mutate)
    with pytest.raises(ValueError):
        lab.check_spec(s)


def test_sweep_parameter_grid_expansion_is_stable_and_definition_only(tmp_path):
    plan = frozen_plan(tmp_path)
    jobs, digest = lab.expand(plan)
    again, same_digest = lab.expand(plan)
    assert len(jobs) == 6
    assert jobs == again
    assert digest == same_digest
    assert len({j["id"] for j in jobs}) == 6
    assert all(j["spec"]["timeframe"] == "M1" for j in jobs)
    dry = lab.run_plan(plan, tmp_path / "not-executed", dry_run=True)
    assert dry["status"] == "DEFINED_ONLY_NO_BACKTEST"
    assert dry["jobs"] == 6
    assert not (tmp_path / "not-executed").exists()


def test_frozen_factory_never_relabels_historical_exposure_as_forward_oos(tmp_path):
    plan = frozen_plan(tmp_path)
    plan["exposure_context"] = "future_prospective"
    with pytest.raises(ValueError):
        lab.expand(plan)
