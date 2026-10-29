"""Synthetic shared-M1 portfolio research only; no original Gold ZIP replay."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import run_frozen_portfolio_mix as mix


def fixture_m1():
    rows=[[100,101,99,100] for _ in range(3)]+[
        [100,100.2,98.2,99.4], [99.4,100.1,99,100],
        [100,104,99.8,103], [103,103.1,102.9,103]
    ]
    return pd.DataFrame(rows,columns=["o","h","l","c"],
        index=pd.date_range("2024-01-01",periods=len(rows),freq="min",tz="UTC"),dtype=float)


def plan(source):
    return {"schema":mix.SCHEMA, "dataset":str(source),
            "source_sha256":mix.SOURCE_SHA, "engine_commit":"a"*40,
            "start":"2024-01-01","end":"2024-01-01",
            "exposure_context":"historical_exposed",
            "components":[
                {"strategy":"m1-sweep","timeframe":"M1","parameters":{
                    "sweep_lookback":3,"sweep_min_excess_usd":.2,
                    "sweep_reclaim_usd":.1,"sweep_stop_buffer_usd":.2,
                    "sweep_reward_risk":2.0,"sweep_max_stop_usd":9.0,
                }},
                {"strategy":"fvg","timeframe":"M15","parameters":{}},
            ],
    }


def test_shared_capacity_executes_once_without_double_counting(monkeypatch,tmp_path):
    source=tmp_path/"fake-source.zip"
    source.write_bytes(b"NOT GOLD")
    cfg=mix.validate_plan(plan(source))
    signals,orders,settings,resolved=mix.compose(fixture_m1(),cfg)
    assert len(signals)==1
    assert len(orders)==0
    assert len(resolved)==2
    assert settings.max_open_positions==1
    assert settings.max_total_ounces==1.0
    assert settings.all_in_cost_per_ounce==.40
    res=mix.run_unified_portfolio(fixture_m1(),signals,orders,settings)
    assert len(res.trades)==1
    assert res.trades.iloc[0]["cost"]==pytest.approx(.40)
    assert res.trades.iloc[0]["net_pnl"]==pytest.approx(2.40)


def test_frozen_shared_runner_is_atomic_and_sha_auditable(monkeypatch,tmp_path):
    source=tmp_path/"private-source.zip"
    source.write_bytes(b"SYNTHETIC_ONLY")
    cfg=plan(source)
    spec=tmp_path/"plan.json"
    spec.write_text(json.dumps(cfg),encoding="utf-8")
    actual_hash=mix.batch.file_sha
    monkeypatch.setattr(mix.batch,"file_sha",
        lambda p: mix.SOURCE_SHA if Path(p)==source else actual_hash(p))
    monkeypatch.setattr(mix.batch,"checkout_commit",lambda:"a"*40)
    monkeypatch.setattr(mix,"load_market",lambda *args:fixture_m1())
    monkeypatch.setattr(mix,"fingerprint_loaded_m1",lambda _: "b"*64)
    destination=tmp_path/"new-mix"
    summary=mix.run_frozen(spec,destination)
    assert summary["trades"]==1
    assert summary["net_pnl_closed"]==pytest.approx(2.4)
    assert destination.is_dir()
    evidence=json.loads((destination/"evidence.json").read_text(encoding="utf-8"))
    assert evidence["independent_oos_proven"] is False
    assert evidence["broker_tick_fills_proven"] is False
    assert evidence["candidate_market_signals"]==1
    assert evidence["candidate_limit_orders"]==0
    assert evidence["max_open_positions"]==1
    assert evidence["cost_all_in_usd_per_ounce"]==.40
    for filename, expected in evidence["source_files"].items():
        assert hashlib.sha256((destination/filename).read_bytes()).hexdigest()==expected
    # Repetition may not overwrite a frozen report or modify its evidence.
    with pytest.raises(ValueError,match="must be new"):
        mix.run_frozen(spec,destination)


@pytest.mark.parametrize("change",[
    {"exposure_context":"future_prospective"},
    {"schema":"UNKNOWN"},
    {"source_sha256":"c"*64},
    {"start":"2027-01-01","end":"2027-01-31"},
    {"start":"2024-01-02","end":"2024-01-01"},
    {"extra":"unexpected"},
])
def test_plan_rejects_unsafe_metadata(tmp_path,change):
    source=tmp_path/"dummy.zip";source.write_bytes(b"SYNTH")
    cfg=plan(source);cfg.update(change)
    with pytest.raises(ValueError):
        mix.validate_plan(cfg)


def test_duplicate_component_cannot_silently_double_fill(tmp_path):
    source=tmp_path/"dummy.zip";source.write_bytes(b"SYNTH")
    cfg=plan(source)
    cfg["components"].append(cfg["components"][0].copy())
    with pytest.raises(ValueError,match="Duplicate"):
        mix.validate_plan(cfg)


def test_unknown_component_field_and_invalid_parameters_fails_before_execution(tmp_path):
    source=tmp_path/"dummy.zip";source.write_bytes(b"SYNTH")
    cfg=plan(source)
    cfg["components"][0]["parameters"]["sweep_lookback"]=True
    with pytest.raises(ValueError):
        mix.validate_plan(cfg)
    cfg=plan(source)
    cfg["components"][1]["magic"]=42
    with pytest.raises(ValueError):
        mix.validate_plan(cfg)
