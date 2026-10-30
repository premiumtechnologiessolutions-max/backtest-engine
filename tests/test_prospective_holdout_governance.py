"""B12: one-candidate prospective holdout, late-trial refusal, source freeze."""
from __future__ import annotations
from datetime import datetime,timezone
from copy import deepcopy
import os,sqlite3
import pytest
from norisk_quant.prospective_holdout_governance import (
    SCHEMA,ProspectiveTrialJournal,validate_protocol,
)
from norisk_quant.scientific_rejection_registry import _hash,strategy_spec
from tests.test_scientific_rejection_registry import plan

NOW=datetime(2026,10,30,0,0,tzinfo=timezone.utc)

def protocol(p):
    return {"schema":SCHEMA,"asset":"XAUUSD","timeframe":"M1",
            "dataset_sha256":p["source_sha256"],"engine_commit":p["engine_commit"],
            "strategy_spec_sha256":_hash(strategy_spec(p)),
            "registered_at_utc":"2026-10-30T00:00:00Z",
            "historical_exposed_through_utc":"2026-10-29T23:00:00Z",
            "train_end_utc":"2026-10-29T23:00:00Z",
            "holdout_start_utc":"2026-12-01T00:00:00Z",
            "holdout_end_exclusive_utc":"2027-03-01T00:00:00Z",
            "trial_budget":1,"fee_usd_per_oz_all_in":0.4,
            "objective":"ALL_COMPLETE_MONTHS_NET_POSITIVE_AFTER_COST"}

def owner(tmp_path):
    p=tmp_path/"private";p.mkdir()
    if os.name=="posix":p.chmod(0o700)
    return p

@pytest.mark.skipif(os.name!="posix",reason="POSIX-only protected study")
def test_frozen_future_record_single_attempt_and_never_auto_approval(tmp_path):
    p=plan(tmp_path)
    j=ProspectiveTrialJournal(owner(tmp_path)/"holdout.sqlite3")
    frozen=protocol(p)
    assert j.freeze(frozen,now=NOW)["registered"] is True
    assert j.freeze(frozen,now=NOW)["registered"] is False
    assert j.declare_trial(p,now=NOW)["accepted"] is True
    assert j.declare_trial(p,now=NOW)["duplicate"] is True
    assert j.status(now=NOW)["state"]=="FUTURE_NOT_OBSERVED"
    assert j.status(now=datetime(2027,3,1,tzinfo=timezone.utc))["state"]=="MANUAL_INDEPENDENT_AUDIT_REQUIRED"
    for at in (NOW,datetime(2027,3,1,tzinfo=timezone.utc)):
        status=j.status(now=at)
        assert status["profitability_verified"] is False
        assert status["approved_for_live"] is False
        assert status["independent_oos"] is False
        assert status["externally_preregistered"] is False

@pytest.mark.parametrize("field,value",[
    ("holdout_start_utc","2026-10-31T00:00:00Z"),
    ("holdout_start_utc","2026-12-01T09:00:00Z"),
    ("holdout_end_exclusive_utc","2026-12-01T00:00:00Z"),
    ("registered_at_utc","2026-10-19T00:00:00Z"),
    ("registered_at_utc","2026-11-01T00:00:00Z"),
    ("train_end_utc","2026-10-31T00:00:00Z"),
    ("historical_exposed_through_utc","2026-11-01T00:00:00Z"),
    ("fee_usd_per_oz_all_in",0.2),
    ("trial_budget",0),("trial_budget",200),
    ("objective","PROFIT_GUARANTEED"),
    ("strategy_spec_sha256","invalid"),
    ("independent_oos",True),
])
def test_invalid_frozen_study_is_rejected(tmp_path,field,value):
    x=protocol(plan(tmp_path));x[field]=value
    with pytest.raises(ValueError):validate_protocol(x,now=NOW)

@pytest.mark.skipif(os.name!="posix",reason="POSIX-only protected study")
def test_mutated_parameters_data_commit_and_protocol_not_allowed(tmp_path):
    p=plan(tmp_path);j=ProspectiveTrialJournal(owner(tmp_path)/"science.sqlite3")
    freeze=protocol(p);j.freeze(freeze,now=NOW)
    altered=deepcopy(freeze);altered["holdout_end_exclusive_utc"]="2027-04-01T00:00:00Z"
    with pytest.raises(ValueError,match="Cannot overwrite"):
        j.freeze(altered,now=NOW)
    for key in ("parameters","source_sha256","engine_commit"):
        new=deepcopy(p)
        if key=="parameters":new["jobs"][0]["parameters"]["sweep_lookback"]=55
        else:new[key]="c"*(64 if key=="source_sha256" else 40)
        with pytest.raises(ValueError,match="differs"):
            j.declare_trial(new,now=NOW)
    assert j.status(now=NOW)["trials_used"]==0

@pytest.mark.skipif(os.name!="posix",reason="POSIX-only protected study")
def test_late_selection_after_holdout_begins_is_forbidden(tmp_path):
    p=plan(tmp_path);j=ProspectiveTrialJournal(owner(tmp_path)/"science.sqlite3")
    j.freeze(protocol(p),now=NOW)
    with pytest.raises(ValueError,match="post-hoc"):
        j.declare_trial(p,now=datetime(2026,12,1,tzinfo=timezone.utc))

@pytest.mark.skipif(os.name!="posix",reason="POSIX-only protected study")
def test_post_registration_history_tamper_fails_closed(tmp_path):
    p=plan(tmp_path);j=ProspectiveTrialJournal(owner(tmp_path)/"science.sqlite3")
    j.freeze(protocol(p),now=NOW);j.declare_trial(p,now=NOW)
    with sqlite3.connect(j.path) as db:
        db.execute("UPDATE trials SET spec_sha=? WHERE seq=1",("f"*64,))
    with pytest.raises(ValueError,match="history was modified"):
        j.status(now=NOW)

@pytest.mark.skipif(os.name!="posix",reason="POSIX-only protected study")
def test_publicly_readable_parent_forbidden(tmp_path):
    folder=tmp_path/"world";folder.mkdir();folder.chmod(0o755)
    with pytest.raises(ValueError,match="0700"):
        ProspectiveTrialJournal(folder/"science.sqlite3")
