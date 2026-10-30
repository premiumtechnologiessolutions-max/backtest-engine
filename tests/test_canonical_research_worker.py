"""B06: operator-triggered, bounded, audited canonical research worker."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
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
    q = ResearchQueue(tmp_path / "operator.sqlite3")
    p = proposal()
    job_id = q.submit(p, now=t())
    if not paused:
        q.set_paused(False, now=t(1))
    output = tmp_path / "local_reports"
    output.mkdir()
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


def test_missing_ledger_artifact_cannot_mark_queue_completed(tmp_path,monkeypatch):
    from norisk_quant import canonical_research_worker as worker
    from scripts import research_batch_orchestrator as batch
    q,p,src,out,id_=setup(tmp_path)
    proof={"experiment_id":id_,"source_manifest_id":"c"*64,"plan":frozen_plan_from_intent(intent(p),data_zip=src)}
    monkeypatch.setattr(worker,"preflight_queued_research",lambda *a,**kw:proof)
    def fake(plan,folder,**kwargs):
        return {"executed_this_invocation":1,"reconciled_jobs":1}
    monkeypatch.setattr(batch,"run_plan",fake)
    with pytest.raises(ValueError,match="Missing bounded"):
        execute_one_approved_job(q,source_manifest={},data_zip=src,checkout=tmp_path,output_root=out)
    assert q.status(id_)["state"]=="rejected"
    assert q.status(id_)["profitability_verified"] is False
    assert q.counts()["completed"]==0


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
