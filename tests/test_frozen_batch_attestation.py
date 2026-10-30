"""B09 independent frozen research evidence: actual CLI, tampering, privacy.

All executable test fixtures contain synthetic quotes, never user/broker data.
The canonical subprocess creates the real historical reports; attestor
must verify their exact bytes before allowing queue completion.
"""
from __future__ import annotations

from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import zipfile

import pytest

from norisk_quant.canonical_research_worker import frozen_plan_from_intent
from norisk_quant.data import sha256_file
from norisk_quant.frozen_batch_attestation import verify_frozen_batch_evidence
from norisk_quant.research_control_plane import SCHEMA, EXTERNAL_SOURCE, proposal_identity
from norisk_quant.source_registry import register_original_gold_m1
from scripts import research_batch_orchestrator as batch
from scripts import verify_frozen_worker_evidence as offline

HEAD="b"*40


@pytest.fixture(scope="module")
def historical_fixture(tmp_path_factory):
    if os.name!="posix":
        pytest.skip("Actual private evidence and permissions are POSIX-only")
    root=tmp_path_factory.mktemp("b09-synthetic")
    src=root/"synthetic_source.zip"
    minute=int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp())
    candles=[]
    for idx in range(280):
        base=2000.0+0.001*idx
        candles.append({
            "ts":minute+idx*60,
            "o":base,"h":base+0.2,"l":base-0.2,"c":base+0.05,
            "ao":base+0.1,"ah":base+0.3,"al":base-0.1,"ac":base+0.15,
        })
    with zipfile.ZipFile(src,"w",compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("XAUUSD_2024.json",json.dumps(candles))
    src.chmod(0o600)
    original=sha256_file(src)
    p={
        "schema":SCHEMA,"producer":EXTERNAL_SOURCE,"agent":"nova",
        "campaign_id":"b09_regression","asset":"XAUUSD",
        "dataset_sha256":original,"engine_commit":HEAD,
        "strategy_id":"m1-sweep",
        "parameters":{"sweep_lookback":20,
                      "sweep_min_excess_usd":0.15,
                      "sweep_reclaim_usd":0.10,
                      "sweep_stop_buffer_usd":0.25,
                      "sweep_reward_risk":2.0,
                      "sweep_max_stop_usd":20.0},
        "timeframe":"M1",
        "window_start_utc":"2024-01-01T00:00:00Z",
        "window_end_exclusive_utc":"2024-02-01T00:00:00Z",
        "quantity_ounces":1.0,"fee_all_in_per_ounce":0.40,
        "execution_mode":"m1_conservative","exposure_context":"historical_exposed",
    }
    job_id,body,_=proposal_identity(p)
    plan=frozen_plan_from_intent(json.loads(body),data_zip=src)
    target=root/"audited-output"
    target.mkdir(mode=0o700)
    original_commit=batch.checkout_commit
    try:
        batch.checkout_commit=lambda: HEAD
        result=batch.run_plan(plan,target,max_jobs=1,dry_run=False,
                              recover_verified_orphans=False)
    finally:
        batch.checkout_commit=original_commit
    assert result["executed_this_invocation"]==1
    assert result["reconciled_jobs"]==1
    source_record=register_original_gold_m1({
        "origin":"user_supplied_gold_m1_bidask",
        "source_file_sha256":original,
        "observed_slice_sha256":"e"*64,
        "rows":280,
        "first_utc":"2024-01-01T00:00:00+00:00",
        "last_utc":"2024-01-01T04:39:00+00:00",
    })
    return {"base":target,"plan":plan,"id":job_id,"source":source_record,
            "root":root}


@pytest.fixture()
def actual(tmp_path,historical_fixture):
    directory=tmp_path/"copied-reports"
    shutil.copytree(historical_fixture["base"],directory)
    directory.chmod(0o700)
    return {**historical_fixture,"output":directory}


def recheck(a):
    return verify_frozen_batch_evidence(
        a["plan"],a["output"],expected_experiment_id=a["id"],
        source_manifest_id=a["source"].id,
    )


def run_dir(a):
    return a["output"]/"runs"/("research-"+a["id"][:32])


def test_actual_canonical_subprocess_evidence_passes_independent_auditor(actual):
    a=recheck(actual)
    assert a.experiment_id==actual["id"]
    assert a.trades>=0
    assert a.months_observed==1
    assert a.execution=="CANONICAL_M1_SYNTHETIC_REFERENCE"
    assert a.manifest_sha256==sha256((actual["output"]/"batch_manifest.json").read_bytes()).hexdigest()
    public=a.public_status()
    assert public["ledger_internal_consistency"]=="PASSED_ON_FROZEN_FILES"
    assert public["profitability_verified"] is False
    assert public["independent_oos"] is False
    assert public["brokerage_fills_verified"] is False
    assert "net_pnl" not in public
    assert actual["plan"]["source_sha256"] not in json.dumps(public)


@pytest.mark.parametrize("name",["trades.csv","weekly.csv","monthly.csv","summary.json"])
def test_single_byte_of_frozen_report_is_detected(actual,name):
    file=run_dir(actual)/name
    with file.open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError,match="evidence|disagree|modified|month|Malformed|Trailing|invalid|numeric|Ragged ledger"):
        recheck(actual)


def test_missing_original_report_cannot_attest(actual):
    (run_dir(actual)/"trades.csv").unlink()
    with pytest.raises(ValueError,match="Missing or unsafe"):
        recheck(actual)


def test_unchanged_file_contents_with_manifest_sha_swap_are_rejected(actual):
    file=actual["output"]/"batch_manifest.json"
    manifest=json.loads(file.read_text())
    key=next(iter(manifest["results"]))
    manifest["results"][key]["monthly_sha256"]="a"*64
    file.write_text(json.dumps(manifest))
    file.chmod(0o600)
    with pytest.raises(ValueError,match="evidence differs"):
        recheck(actual)


def test_manifest_claiming_a_different_engine_commit_is_rejected(actual):
    file=actual["output"]/"batch_manifest.json"
    manifest=json.loads(file.read_text())
    manifest["engine_commit"]="f"*40
    file.write_text(json.dumps(manifest))
    file.chmod(0o600)
    with pytest.raises(ValueError,match="source/plan/engine/job"):
        recheck(actual)


def test_manifest_with_extra_unknown_job_cannot_be_certified(actual):
    file=actual["output"]/"batch_manifest.json"
    manifest=json.loads(file.read_text())
    manifest["results"]["research-injected"]={"status":"PASSED"}
    file.write_text(json.dumps(manifest))
    file.chmod(0o600)
    with pytest.raises(ValueError,match="source/plan/engine/job"):
        recheck(actual)


def test_forged_queue_experiment_does_not_match_the_real_ledger(actual):
    with pytest.raises(ValueError,match="job ID differs"):
        verify_frozen_batch_evidence(
            actual["plan"],actual["output"],
            expected_experiment_id="f"*64,
            source_manifest_id=actual["source"].id,
        )


def test_plan_source_hash_change_cannot_be_accepted(actual):
    plan=dict(actual["plan"],source_sha256="f"*64)
    with pytest.raises(ValueError,match="source/plan/engine/job"):
        verify_frozen_batch_evidence(
            plan,actual["output"],
            expected_experiment_id=actual["id"],
            source_manifest_id=actual["source"].id,
        )


def test_symlinked_report_file_is_forbidden(actual,tmp_path):
    file=run_dir(actual)/"monthly.csv"
    original=tmp_path/"original.csv"
    shutil.copyfile(file,original)
    file.unlink()
    file.symlink_to(original)
    with pytest.raises(ValueError,match="Missing or unsafe"):
        recheck(actual)


@pytest.mark.skipif(os.name!="posix",reason="POSIX link test")
def test_hardlinked_report_file_is_forbidden(actual,tmp_path):
    file=run_dir(actual)/"weekly.csv"
    link=tmp_path/"other.csv"
    os.link(file,link)
    with pytest.raises(ValueError,match="hardlink"):
        recheck(actual)


def test_world_readable_original_report_rejected(actual):
    file=run_dir(actual)/"summary.json"
    file.chmod(0o644)
    with pytest.raises(ValueError,match="owner-only"):
        recheck(actual)


def test_failed_research_run_cannot_be_marked_as_passed(actual):
    file=actual["output"]/"batch_manifest.json"
    manifest=json.loads(file.read_text())
    key=next(iter(manifest["results"]))
    manifest["results"][key]={"status":"FAILED_REQUIRES_INVESTIGATION"}
    file.write_text(json.dumps(manifest))
    file.chmod(0o600)
    with pytest.raises(ValueError,match="Failed/orphaned"):
        recheck(actual)


def test_cli_offline_reaudit_does_not_echo_raw_pnl_or_private_paths(actual,tmp_path,capsys):
    root=tmp_path/"operator-private"
    root.mkdir(mode=0o700)
    plan=root/"plan.json"
    source=root/"month-manifest.json"
    plan.write_text(json.dumps(actual["plan"]),encoding="utf-8")
    source.write_text(json.dumps(actual["source"].internal_manifest()),encoding="utf-8")
    assert offline.main([
        "--plan",str(plan),"--source-manifest",str(source),
        "--output",str(actual["output"]),
        "--experiment-id",actual["id"],
    ])==0
    logged=capsys.readouterr().out
    visible=json.loads(logged)
    assert visible["independent_oos"] is False
    assert visible["risk_approved"] is False
    assert visible["profitability_verified"] is False
    assert "net_pnl" not in logged
    assert "source_file_sha256" not in logged
    assert str(root) not in logged


def test_cli_mismatched_source_manifest_rejects_without_private_message(actual,tmp_path,capsys):
    root=tmp_path/"private"
    root.mkdir()
    p=root/"plan.json"
    manifest=root/"source.json"
    p.write_text(json.dumps(actual["plan"]))
    tampered=actual["source"].internal_manifest()
    tampered["record"]["source_file_sha256"]="f"*64
    manifest.write_text(json.dumps(tampered))
    with pytest.raises(SystemExit) as e:
        offline.main(["--plan",str(p),"--source-manifest",str(manifest),
                      "--output",str(actual["output"]),
                      "--experiment-id",actual["id"]])
    assert e.value.code==2
    text=capsys.readouterr().err
    assert "f"*64 not in text
    assert str(root) not in text
