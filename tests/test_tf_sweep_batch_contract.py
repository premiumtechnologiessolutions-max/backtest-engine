"""Frozen parameter-grid contract for existing M15/H1 sweep strategy."""
import pytest
from scripts import research_batch_orchestrator as batch


def spec(tf="M15", params=None):
    return {
        "strategy": "tf-sweep", "timeframe": tf, "execution": "reference",
        "start": "2012-01-01", "end": "2012-12-31",
        "parameters": params if params is not None else {
            "tf_sweep_lookback_bars": 12,
            "tf_sweep_penetration_usd": 0.25,
            "tf_sweep_stop_buffer_usd": 0.10,
            "tf_sweep_reward_risk": 1.5,
            "tf_sweep_min_stop_usd": 0.5,
            "tf_sweep_max_stop_usd": 50.0,
        }
    }


@pytest.mark.parametrize("tf",["M15","H1"])
@pytest.mark.parametrize("execution",["fast","reference"])
def test_frozen_tf_sweep_explicit_timeframes_and_engines(tf,execution):
    item=spec(tf)
    item["execution"]=execution
    assert batch.check_spec(item)["execution"]==execution


@pytest.mark.parametrize("tf", ["M1","M5","H4"])
def test_frozen_tf_sweep_refuses_other_timeframes(tf):
    with pytest.raises(ValueError):
        batch.check_spec(spec(tf))


@pytest.mark.parametrize("params",[
    {"tf_sweep_lookback_bars": 2},
    {"tf_sweep_lookback_bars": True},
    {"tf_sweep_lookback_bars": 3.5},
    {"tf_sweep_penetration_usd": 0},
    {"tf_sweep_penetration_usd": float("inf")},
    {"tf_sweep_reward_risk": float("nan")},
    {"tf_sweep_min_stop_usd": 55, "tf_sweep_max_stop_usd": 50},
    {"unknown": 1},
])
def test_bad_frozen_tf_sweep_params_rejected(params):
    with pytest.raises(ValueError):
        batch.check_spec(spec(params=params))


def test_tf_sweep_grid_is_frozen_and_not_an_executed_backtest(tmp_path):
    plan={
        "schema":batch.SCHEMA, "dataset":str(tmp_path/"private.zip"),
        "source_sha256":"a"*64, "engine_commit":"b"*40,
        "exposure_context":"historical_exposed", "jobs":[],
        "grids":[{
            "id_prefix":"tf-sweep", "strategy":"tf-sweep",
            "timeframe":"M15", "execution":"reference",
            "start":"2012-01-01","end":"2012-12-31",
            "grid":{"tf_sweep_lookback_bars":[12,20],
                    "tf_sweep_reward_risk":[1.0,1.5,2.0]}
        }]
    }
    jobs, sha=batch.expand(plan)
    assert len(jobs)==6
    assert len({j["id"] for j in jobs})==6
    assert batch.expand(plan)==(jobs,sha)
    status=batch.run_plan(plan,tmp_path/"output",dry_run=True)
    assert status["status"]=="DEFINED_ONLY_NO_BACKTEST"
    assert not (tmp_path/"output").exists()
