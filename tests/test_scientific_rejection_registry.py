"""B11: deterministic scientific rejection, chain corruption, no OOS promotion."""
from __future__ import annotations
from copy import deepcopy
import json, os, sqlite3
import pytest
from norisk_quant.scientific_rejection_registry import (
    ScientificDecisionJournal, _hash, _verify_evidence, strategy_spec, SCHEMA
)
from norisk_quant.research_control_plane import proposal_identity,SCHEMA as QSCHEMA,EXTERNAL_SOURCE

def plan(tmp, *, year=2012,commit="b"*40,parameters=None):
    src=tmp/"synthetic.zip";src.write_bytes(b"SIMULATED DATA ONLY")
    original={"schema":QSCHEMA,"producer":EXTERNAL_SOURCE,"agent":"nova",
              "campaign_id":"b11_synthetic_test","asset":"XAUUSD",
              "dataset_sha256":"a"*64,"engine_commit":commit,"strategy_id":"m1-sweep",
              "parameters":parameters or {"sweep_lookback":20,"sweep_min_excess_usd":0.15,
                 "sweep_reclaim_usd":0.1,"sweep_stop_buffer_usd":0.25,
                 "sweep_reward_risk":2.0,"sweep_max_stop_usd":20.0},
              "timeframe":"M1","window_start_utc":f"{year}-01-01T00:00:00Z",
              "window_end_exclusive_utc":f"{year+1}-01-01T00:00:00Z",
              "quantity_ounces":1.0,"fee_all_in_per_ounce":0.4,
              "execution_mode":"m1_conservative","exposure_context":"historical_exposed"}
    job_id,_,_=proposal_identity(original)
    return {"schema":"NRFX_FROZEN_BATCH_V1","dataset":str(src),"source_sha256":"a"*64,
            "engine_commit":commit,"exposure_context":"historical_exposed","grids":[],
            "jobs":[{"id":"research-"+job_id[:32],"strategy":"m1-sweep",
                     "timeframe":"M1","execution":"reference",
                     "start":f"{year}-01-01","end":f"{year}-12-31",
                     "parameters":original["parameters"]}]}

def evidence(plan, year,positive=0):
    s=strategy_spec(plan)
    months=[{"period":f"{year}-{i:02d}","net_usd":"1.00" if i<=positive else "-2.00",
             "trades":4,"all_in_cost_usd":"1.60"} for i in range(1,13)]
    row={"schema":SCHEMA,"spec":s,"spec_sha256":_hash(s),
         "exposure":"HISTORICAL_EXPOSED_NOT_OOS",
         "disposition":"HISTORICAL_ONLY_NOT_APPROVED" if positive==12 else "REJECTED_HISTORICAL_MONTHLY_OBJECTIVE",
         "year":year,"monthly":months,"positive_months":positive,"months_observed":12,
         "trades":48,"total_net_usd":str(sum(1 if i<=positive else -2 for i in range(1,13))),
         "original_source_sha256":"a"*64,"source_manifest_id":"c"*64,
         "engine_commit":plan["engine_commit"],"plan_sha256":"d"*64,
         "batch_manifest_sha256":"e"*64,"experiment_id":"f"*64,
         "out_of_sample":False,"broker_fills_verified":False,
         "profitability_verified":False,"approved_for_live":False}
    _verify_evidence(row)
    return row

@pytest.fixture
def owner(tmp_path):
    folder=tmp_path/"private";folder.mkdir()
    if os.name=="posix":folder.chmod(0o700)
    return folder

@pytest.mark.skipif(os.name!="posix",reason="POSIX private evidence only")
def test_same_strategy_cannot_reappear_as_new_discovery(owner):
    j=ScientificDecisionJournal(owner/"registry.sqlite3")
    p12=plan(owner)
    r12=evidence(p12,2012)
    assert j.append(r12)["recorded"] is True
    assert j.append(r12)["recorded"] is False
    p24=plan(owner,year=2024)
    r24=evidence(p24,2024);r24["experiment_id"]="1"*64
    j.append(r24)
    assert j.audit()["evidence_count"]==2
    for case in (p12,p24,plan(owner,year=2024,commit="9"*40)):
        gate=j.candidate_gate(case)
        assert gate["decision"]=="BLOCK_IDENTICAL_PREVIOUSLY_REJECTED"
        assert gate["same_spec_evidence_count"]==2
        assert gate["approved_for_live"] is False

@pytest.mark.skipif(os.name!="posix",reason="POSIX private evidence only")
def test_new_parameter_is_not_independent_holdout(owner):
    j=ScientificDecisionJournal(owner/"science.sqlite3")
    original=plan(owner);j.append(evidence(original,2012))
    changed=deepcopy(original);changed["jobs"][0]["parameters"]["sweep_lookback"]=30
    gate=j.candidate_gate(changed)
    assert gate["decision"]=="HISTORICAL_EXPOSED_FAMILY_VARIANT"
    assert gate["independent_oos"] is False
    assert gate["autonomous_promotion"] is False

@pytest.mark.skipif(os.name!="posix",reason="POSIX private evidence only")
def test_all_twelve_historical_wins_cannot_approve_live(owner):
    j=ScientificDecisionJournal(owner/"science.sqlite3")
    p=plan(owner);j.append(evidence(p,2012,positive=12))
    assert j.candidate_gate(p)["decision"]=="HISTORICAL_RESEARCH_ONLY_ALREADY_TESTED"
    assert j.candidate_gate(p)["profitability_verified"] is False

@pytest.mark.skipif(os.name!="posix",reason="POSIX private evidence only")
def test_chain_mutation_and_missing_middle_record_fails(owner):
    j=ScientificDecisionJournal(owner/"science.sqlite3")
    for yr in (2012,2024,2019):
        r=evidence(plan(owner,year=yr),yr);r["experiment_id"]=str(yr)[0]*64
        j.append(r)
    with sqlite3.connect(j.path) as c:
        c.execute("DELETE FROM evidence WHERE seq=2")
    with pytest.raises(ValueError,match="Missing/forked"):
        j.audit()

@pytest.mark.parametrize("field,value", [
    ("approved_for_live",True),("out_of_sample",True),
    ("broker_fills_verified",True),("profitability_verified",True),
    ("disposition","PROVEN_EDGE"),("months_observed",11),
    ("positive_months",12),("trades",1000),("total_net_usd","1000.00"),
])
def test_untrusted_ai_cannot_self_authorize_evidence(owner,field,value):
    row=evidence(plan(owner),2012)
    row[field]=value
    with pytest.raises(ValueError):_verify_evidence(row)

def test_missing_month_and_forged_fee_cannot_be_stored(owner):
    for bad in ("missing","fee"):
        r=evidence(plan(owner),2012)
        if bad=="missing":r["monthly"]=r["monthly"][:-1]
        else:r["monthly"][0]["all_in_cost_usd"]="0.0"
        with pytest.raises(ValueError):_verify_evidence(r)

@pytest.mark.skipif(os.name!="posix",reason="POSIX private evidence only")
def test_public_gate_never_includes_original_market_pnl(owner):
    j=ScientificDecisionJournal(owner/"science.sqlite3")
    p=plan(owner);j.append(evidence(p,2012))
    public=json.dumps(j.candidate_gate(p))
    for private in ("-2.00","source_manifest_id","broker_password","net_usd"):
        assert private not in public
    assert j.audit()["externally_anchored"] is False
