"""B06: operator-triggered, bounded, audited canonical research worker."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
import zipfile
from pathlib import Path

import pytest

from norisk_quant.canonical_research_worker import (
    frozen_plan_from_intent, preflight_queued_research,
    execute_one_approved_job,
)
from norisk_quant.research_control_plane import (
    EXTERNAL_SOURCE, SCHEMA, Lease, ResearchQueue, proposal_identity,
)

HEAD = "b" * 40
SRC = "a" * 64
WHEN = datetime(2026,10,30,0,0,0,tzinfo=timezone.utc)


def t(s=0):
    return WHEN + timedelta(seconds=s)


def proposal():
    return {
        "schema": SCHEMA, "producer": EXTERNAL_SOURCE, "agent": "nova",
        "campaign_id": "b06_test", "asset": "XAUUSD",
        "dataset_sha256": SRC, "engine_commit": HEAD,
        "strategy_id": "m1-sweep",
        "parameters": {
            "sweep_lookback": 20, "sweep_min_excess_usd": 0.15,
            "sweep_reclaim_usd": 0.10, "sweep_stop_buffer_usd": 0.25,
            "sweep_reward_risk": 2.0, "sweep_max_stop_usd": 20.0,
        },
        "timeframe": "M1", "window_start_utc": "2024-01-01T00:00:00Z",
        "window_end_exclusive_utc": "2024-02-01T00:00:00Z",
        "quantity_ounces": 1.0, "fee_all_in_per_ounce": 0.40,
        "execution_mode": "m1_conservative",
        "exposure_context": "historical_exposed",
    }


def setup(tmp_path, *, paused=False):
    source = tmp_path / "source.zip"
    source.write_bytes(b"synthetic offline only")
    if os.name == "posix":
        source.chmod(0o600)
    q = ResearchQueue(tmp_path / "operator.sqlite3")
    p = proposal()
    job_id = q.submit(p, now=t())
    if not paused:
        q.set_paused(False, now=t(1))
    output = tmp_path / "local_reports"
    output.mkdir()
    if os.name == "posix":
        output.chmod(0o700)
    return q, p, source, output, job_id


def intent(p):
    identity, body, agent = proposal_identity(p)
    assert agent == "nova"
    return json.loads(body)


def test_canonical_frozen_month_strategy_plan_is_exact_and_cost_safe(tmp_path):
    q, p, src, out, id_ = setup(tmp_path)
    plan = frozen_plan_from_intent(intent(p), data_zip=src)
    assert plan["schema"] == "NRFX_FROZEN_BATCH_V1"
    assert plan["source_sha256"] == SRC
    assert plan["engine_commit"] == HEAD
    assert plan["exposure_context"] == "historical_exposed"
    assert len(plan["jobs"]) == 1
    job = plan["jobs"][0]
    assert job["id"].startswith("research-")
    assert job["strategy"] == "m1-sweep"
    assert job["execution"] == "reference"
    assert job["start"] == "2024-01-01"
    assert job["end"] == "2024-01-31"
    assert job["parameters"] == p["parameters"]


@pytest.mark.parametrize("bad,match",[
    ({"strategy_id":"aql_fff001"}, "not mapped"),
    ({"strategy_id":"ema"}, "not mapped"),
    ({"strategy_id":"m1-sweep; echo secret"}, "strategy"),
    ({"timeframe":"H1"}, "conservative M1"),
    ({"execution_mode":"observed_tick_research"}, "conservative"),
    ({"exposure_context":"future_prospective"}, "future prospective"),
    ({"quantity_ounces":0.02}, "one-ounce"),
    ({"window_start_utc":"2024-01-01T02:00:00Z"}, "full-day"),
    ({"window_start_utc":"2024-01-02T00:00:00Z"}, "full-calendar-month"),
    ({"window_end_exclusive_utc":"2024-03-01T00:00:00Z"}, "one full UTC"),
    ({"window_end_exclusive_utc":"2023-12-31T00:00:00Z"}, "interval"),
    ({"fee_all_in_per_ounce":0.8}, "0.40"),
    ({"parameters":{"eval":1}}, "Unknown canonical"),
])
def test_unapproved_strategy_or_unsafe_experiment_must_not_run(tmp_path,bad,match):
    q,p,src,out,id_ = setup(tmp_path)
    p.update(bad)
    with pytest.raises(ValueError, match=match):
        frozen_plan_from_intent(intent(p), data_zip=src)


def test_valid_declaration_cannot_use_nonstrategy_versioned_external_agent_id(tmp_path):
    q,p,src,out,id_ = setup(tmp_path)
    p["strategy_id"] = "aql_bbbccaa"
    with pytest.raises(ValueError,match="not mapped"):
        frozen_plan_from_intent(intent(p),data_zip=src)


def test_uncommitted_pnl_cannot_enter_experiment_identity(tmp_path):
    q,p,src,out,id_ = setup(tmp_path)
    p["profit_usd"]=1e9
    with pytest.raises(ValueError, match="schema"):
        proposal_identity(p)


def test_queue_lease_can_read_only_its_own_frozen_intent(tmp_path):
    q,p,src,out,id_ = setup(tmp_path)
    lease=q.claim(worker="canonical_runner",now=t(2),lease_seconds=120)
    assert lease
    private=q.leased_research_intent(lease,now=t(3))
    assert private["canonical_experiment_id"]==id_
    assert private["parameters"]==p["parameters"]
    assert "profit" not in str(private)
    forged=Lease(lease.job_id,lease.attempt,"fake",lease.expires_utc)
    with pytest.raises(ValueError,match="lease"):
        q.leased_research_intent(forged,now=t(4))


def test_revoked_or_expired_lease_cannot_read_intent(tmp_path):
    q,p,src,out,id_=setup(tmp_path)
    lease=q.claim(worker="canonical_runner",now=t(2),lease_seconds=10)
    q.set_paused(True,now=t(3))
    with pytest.raises(ValueError,match="paused"):
        q.leased_research_intent(lease,now=t(4))
    q.set_paused(False,now=t(5))
    with pytest.raises(ValueError,match="lease"):
        q.leased_research_intent(lease,now=t(6))


def test_lease_expires_without_heartbeat(tmp_path):
    q,p,src,out,id_=setup(tmp_path)
    lease=q.claim(worker="canonical_runner",now=t(2),lease_seconds=10)
    with pytest.raises(ValueError,match="lease"):
        q.leased_research_intent(lease,now=t(12))


def test_no_auto_queue_execution_when_operator_paused(tmp_path):
    q,p,src,out,id_=setup(tmp_path,paused=True)
    result=execute_one_approved_job(
        q,source_manifest={},data_zip=src,checkout=tmp_path,output_root=out
    )
    assert result["execution"]=="NONE"
    assert result["status"]=="PAUSED_OR_EMPTY_OR_BUSY"
    assert q.status(id_)["state"]=="queued"


@pytest.mark.skipif(os.name != "posix", reason="Canonical private evidence execution requires POSIX mode controls")
def test_successful_canonical_auditor_only_commits_artifact_pointer(tmp_path,monkeypatch):
    from norisk_quant import canonical_research_worker as worker
    from scripts import research_batch_orchestrator as batch
    q,p,src,out,id_=setup(tmp_path)
    proof={"experiment_id":id_,"source_manifest_id":"c"*64,
           "plan":frozen_plan_from_intent(intent(p),data_zip=src)}
    monkeypatch.setattr(worker,"preflight_queued_research",lambda *a,**kw:proof)
    def audited(plan,folder,**kwargs):
        assert kwargs["dry_run"] is False
        assert kwargs["max_jobs"]==1
        assert plan==proof["plan"]
        folder.mkdir(parents=True,exist_ok=True)
        (folder/"batch_manifest.json").write_bytes(b'{"simulation":"historical-only"}')
        return {"executed_this_invocation":1,"reconciled_jobs":1}
    monkeypatch.setattr(batch,"run_plan",audited)
    # This legacy test mocks the runner: the separate B09 suite below
    # exercises actual on-disk independent attestation end-to-end.
    from types import SimpleNamespace
    def attest(plan,folder,**kwargs):
        assert kwargs["expected_experiment_id"]==id_
        assert kwargs["source_manifest_id"]=="c"*64
        return SimpleNamespace(manifest_sha256=sha256(b'{"simulation":"historical-only"}').hexdigest())
    monkeypatch.setattr(worker,"verify_frozen_batch_evidence",attest)
    result=execute_one_approved_job(
        q,source_manifest={},data_zip=src,checkout=tmp_path,output_root=out,
    )
    assert result["status"]=="HISTORICAL_RESEARCH_ARTIFACT_RECORDED_NOT_APPROVED"
    assert result["profitability_verified"] is False
    assert result["independent_oos"] is False
    assert result["live_execution"] is False
    assert result["research_artifact_sha256"] == sha256(b'{"simulation":"historical-only"}').hexdigest()
    assert q.status(id_)["state"]=="completed"
    assert q.status(id_)["profitability_verified"] is False
    assert q.counts()["completed"]==1
    assert q.counts()["queued"]==0
    assert q.audit(id_)[-1]["event_type"]=="research_artifact_recorded"
    second=execute_one_approved_job(
        q,source_manifest={},data_zip=src,checkout=tmp_path,output_root=out,
    )
    assert second["status"]=="PAUSED_OR_EMPTY_OR_BUSY"


@pytest.mark.skipif(os.name != "posix", reason="Canonical private evidence execution requires POSIX mode controls")
def test_missing_ledger_artifact_cannot_mark_queue_completed(tmp_path,monkeypatch):
    from norisk_quant import canonical_research_worker as worker
    from scripts import research_batch_orchestrator as batch
    q,p,src,out,id_=setup(tmp_path)
    proof={"experiment_id":id_,"source_manifest_id":"c"*64,"plan":frozen_plan_from_intent(intent(p),data_zip=src)}
    monkeypatch.setattr(worker,"preflight_queued_research",lambda *a,**kw:proof)
    def fake(plan,folder,**kwargs):
        return {"executed_this_invocation":1,"reconciled_jobs":1}
    monkeypatch.setattr(batch,"run_plan",fake)
    with pytest.raises(ValueError,match="Missing or unsafe"):
        execute_one_approved_job(q,source_manifest={},data_zip=src,checkout=tmp_path,output_root=out)
    assert q.status(id_)["state"]=="rejected"
    assert q.status(id_)["profitability_verified"] is False
    assert q.counts()["completed"]==0


@pytest.mark.skipif(os.name != "posix", reason="Canonical private evidence execution requires POSIX mode controls")
def test_failed_canonical_audit_does_not_retry_automatically(tmp_path,monkeypatch):
    from norisk_quant import canonical_research_worker as worker
    from scripts import research_batch_orchestrator as batch
    q,p,src,out,id_=setup(tmp_path)
    proof={"experiment_id":id_,"source_manifest_id":"c"*64,"plan":frozen_plan_from_intent(intent(p),data_zip=src)}
    monkeypatch.setattr(worker,"preflight_queued_research",lambda *a,**kw:proof)
    def fail(*a,**kw):
        raise RuntimeError("bad audited ledger")
    monkeypatch.setattr(batch,"run_plan",fail)
    with pytest.raises(RuntimeError,match="bad audited ledger"):
        execute_one_approved_job(q,source_manifest={},data_zip=src,checkout=tmp_path,output_root=out)
    assert q.status(id_)["state"]=="rejected"
    assert q.counts()["queued"]==0
    assert q.counts()["completed"]==0
    assert q.audit(id_)[-1]["event_type"]=="proposal_rejected"


def test_manifest_binding_is_checked_before_canonical_runner_can_launch(tmp_path,monkeypatch):
    from norisk_quant import canonical_research_worker as worker
    from scripts import research_batch_orchestrator as batch
    q,p,src,out,id_=setup(tmp_path)
    def reject(*args,**kw):
        raise ValueError("Original ZIP SHA or quote integrity differs")
    monkeypatch.setattr(worker,"preflight_queued_research",reject)
    def forbidden(*args,**kw):
        raise AssertionError("Canonical execution was called before source QA")
    monkeypatch.setattr(batch,"run_plan",forbidden)
    with pytest.raises(ValueError,match="Original ZIP"):
        execute_one_approved_job(q,source_manifest={},data_zip=src,checkout=tmp_path,output_root=out)
    assert q.status(id_)["state"]=="rejected"
    assert not list(out.iterdir())


def test_operator_cli_defaults_to_nonexecuting_status(tmp_path,capsys):
    from scripts.canonical_research_worker import main
    q,p,src,out,id_=setup(tmp_path,paused=True)
    assert main(["--queue-db",str(q.path)])==0
    result=json.loads(capsys.readouterr().out)
    assert result["execution"]=="NONE_STATUS_ONLY"
    assert result["counts"]["queued"]==1
    assert result["counts"]["paused"] is True


def test_operator_cli_requires_explicit_resume_and_execute(tmp_path,capsys):
    from scripts.canonical_research_worker import main
    q,p,src,out,id_=setup(tmp_path,paused=True)
    assert main(["--queue-db",str(q.path),"--resume"])==0
    assert ResearchQueue(q.path).counts()["paused"] is False
    capsys.readouterr()
    assert main(["--queue-db",str(q.path),"--pause"])==0
    assert ResearchQueue(q.path).counts()["paused"] is True
    capsys.readouterr()
    with pytest.raises(SystemExit) as result:
        main(["--queue-db",str(q.path),"--execute"])
    assert result.value.code==2
    assert ResearchQueue(q.path).counts()["queued"]==1


def test_actual_source_pipeline_accepts_closed_month_edge_without_fabrication(tmp_path,monkeypatch):
    from norisk_quant import canonical_research_worker as worker
    from norisk_quant.data import load_market,sha256_file,fingerprint_loaded_m1
    from norisk_quant.source_registry import register_original_gold_m1
    source=tmp_path/"original_gold.zip"
    def candle(when):
        return {"ts":int(datetime.fromisoformat(when).timestamp()),
                "o":2000,"h":2002,"l":1999,"c":2001,
                "ao":2000.2,"ah":2002.2,"al":1999.2,"ac":2001.2}
    rows=[candle("2024-01-02T23:00:00+00:00"),candle("2024-01-31T23:59:00+00:00")]
    with zipfile.ZipFile(source,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("XAUUSD_2024.json",json.dumps(rows))
    frame=load_market(source,"2024-01-01","2024-01-31")
    metadata={
        "origin":"user_supplied_gold_m1_bidask",
        "source_file_sha256":sha256_file(source),
        "observed_slice_sha256":fingerprint_loaded_m1(frame),
        "rows":len(frame),
        "first_utc":frame.index[0].isoformat(),
        "last_utc":frame.index[-1].isoformat(),
    }
    manifest=register_original_gold_m1(metadata).internal_manifest()
    p=proposal()
    p["dataset_sha256"]=sha256_file(source)
    private_intent=intent(p)
    monkeypatch.setattr(worker,"inspect_local_checkout",lambda _:HEAD)
    preview=preflight_queued_research(
        private_intent,source_manifest=manifest,data_zip=source,checkout=tmp_path)
    assert preview["experiment_id"]==private_intent["canonical_experiment_id"]
    assert preview["source_manifest_id"]==manifest["id"]
    assert preview["execution"]=="NONE_PREFLIGHT_ONLY"
    assert preview["independent_oos"] is False
    assert len(frame)==2  # no fabricated in-between M1 candles


def test_unbounded_calendar_edge_missing_observations_remain_rejected(tmp_path,monkeypatch):
    from norisk_quant import canonical_research_worker as worker
    from norisk_quant.data import load_market,sha256_file,fingerprint_loaded_m1
    from norisk_quant.source_registry import register_original_gold_m1
    source=tmp_path/"source.zip"
    def row(when):
        return {"ts":int(datetime.fromisoformat(when).timestamp()),
                "o":2000,"h":2002,"l":1999,"c":2001,
                "ao":2000.2,"ah":2002.2,"al":1999.2,"ac":2001.2}
    with zipfile.ZipFile(source,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("XAUUSD_2024.json",json.dumps([
            row("2024-01-05T00:00:00+00:00"),
            row("2024-01-31T23:59:00+00:00"),
        ]))
    frame=load_market(source,"2024-01-01","2024-01-31")
    meta=register_original_gold_m1({
        "origin":"user_supplied_gold_m1_bidask",
        "source_file_sha256":sha256_file(source),
        "observed_slice_sha256":fingerprint_loaded_m1(frame),
        "rows":len(frame),"first_utc":frame.index[0].isoformat(),
        "last_utc":frame.index[-1].isoformat(),
    }).internal_manifest()
    p=proposal()
    p["dataset_sha256"]=sha256_file(source)
    monkeypatch.setattr(worker,"inspect_local_checkout",lambda _:HEAD)
    with pytest.raises(ValueError,match="before the available"):
        preflight_queued_research(intent(p),source_manifest=meta,data_zip=source,checkout=tmp_path)


@pytest.mark.skipif(os.name == "posix", reason="Windows-only NTFS evidence restriction")
def test_windows_canonical_execution_fails_closed_before_invoking_runner(tmp_path,monkeypatch):
    from norisk_quant import canonical_research_worker as worker
    from scripts import research_batch_orchestrator as batch
    q,p,src,out,job=setup(tmp_path)
    proof={"experiment_id":job,"source_manifest_id":"c"*64,
           "plan":frozen_plan_from_intent(intent(p),data_zip=src)}
    monkeypatch.setattr(worker,"preflight_queued_research",lambda *a,**kw:proof)
    def forbidden(*args,**kw):
        raise AssertionError("Unsafe Windows canonical execution must never run")
    monkeypatch.setattr(batch,"run_plan",forbidden)
    with pytest.raises(ValueError,match="requires reviewed POSIX evidence permissions"):
        execute_one_approved_job(q,source_manifest={},data_zip=src,checkout=tmp_path,output_root=out)
    assert q.status(job)["state"]=="rejected"
    assert q.counts()["completed"]==0


@pytest.mark.skipif(os.name != "posix",reason="Canonical evidence writes require POSIX permissions")
def test_real_canonical_runner_creates_audited_month_week_trade_files(tmp_path,monkeypatch):
    """Actually run norisk_quant.cli on a made-up ZIP; no broker or user data."""
    from norisk_quant import canonical_research_worker as worker
    from scripts import research_batch_orchestrator as batch
    from norisk_quant.data import sha256_file
    src=tmp_path/"synthetic_market_2024.zip"
    first=int(datetime.fromisoformat("2024-01-01T00:00:00+00:00").timestamp())
    candles=[]
    for idx in range(280):
        price=2000.0+0.001*idx
        candles.append({
            "ts":first+idx*60, "o":price, "h":price+0.20,
            "l":price-0.20, "c":price+0.05,
            "ao":price+0.10, "ah":price+0.30,
            "al":price-0.10, "ac":price+0.15,
        })
    with zipfile.ZipFile(src,"w",compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("XAUUSD_2024.json",json.dumps(candles))
    p=proposal()
    p["dataset_sha256"]=sha256_file(src)
    q=ResearchQueue(tmp_path/"queue.sqlite3")
    id_=q.submit(p,now=t())
    q.set_paused(False,now=t(1))
    folder=tmp_path/"reports"
    folder.mkdir()
    if os.name == "posix":
        folder.chmod(0o700)
        src.chmod(0o600)
    expected_plan=frozen_plan_from_intent(intent(p),data_zip=src)
    proof={"experiment_id":id_,"source_manifest_id":"f"*64,"plan":expected_plan}
    monkeypatch.setattr(worker,"preflight_queued_research",lambda *a,**kw:proof)
    monkeypatch.setattr(batch,"checkout_commit",lambda:HEAD)
    outcome=execute_one_approved_job(
        q,source_manifest={},data_zip=src,checkout=tmp_path,output_root=folder,
    )
    assert outcome["status"]=="HISTORICAL_RESEARCH_ARTIFACT_RECORDED_NOT_APPROVED"
    assert outcome["profitability_verified"] is False
    assert outcome["broker_fill_parity"] is False
    root=folder/id_
    assert (root/"batch_manifest.json").is_file()
    manifest=json.loads((root/"batch_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_sha256"]==sha256_file(src)
    assert len(manifest["results"])==1
    runs=list((root/"runs").iterdir())
    assert len(runs)==1
    for file in ("summary.json","trades.csv","weekly.csv","monthly.csv"):
        assert (runs[0]/file).is_file(),file
    assert q.status(id_)["state"]=="completed"
    assert q.status(id_)["risk_approved"] is False
    assert q.counts()["completed"]==1


@pytest.mark.skipif(os.name != "posix",reason="POSIX owner-only permissions contract")
@pytest.mark.parametrize("unsafe", ["source", "output", "queue"])
def test_posix_private_file_permissions_must_be_approved_before_runner(tmp_path,monkeypatch,unsafe):
    from norisk_quant import canonical_research_worker as worker
    from scripts import research_batch_orchestrator as batch
    q,p,source,output,job=setup(tmp_path)
    proof={"experiment_id":job,"source_manifest_id":"c"*64,
           "plan":frozen_plan_from_intent(intent(p),data_zip=source)}
    monkeypatch.setattr(worker,"preflight_queued_research",lambda *a,**kw:proof)
    def forbidden(*a,**kw):
        raise AssertionError("Canonical subprocess executed despite insecure local permissions")
    monkeypatch.setattr(batch,"run_plan",forbidden)
    target={"source":source,"output":output,"queue":q.path}[unsafe]
    target.chmod(0o755 if unsafe=="output" else 0o644)
    with pytest.raises(ValueError,match="owner-only"):
        execute_one_approved_job(q,source_manifest={},data_zip=source,
                                 checkout=tmp_path,output_root=output)
    assert q.status(job)["state"]=="rejected"
    assert q.counts()["completed"]==0
