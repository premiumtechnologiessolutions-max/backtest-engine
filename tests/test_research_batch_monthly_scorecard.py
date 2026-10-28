"""Synthetic scorecard checks; never uses original Gold ZIP."""
import hashlib
import json
from pathlib import Path
import pytest
from scripts import research_batch_monthly_scorecard as score
from scripts import research_batch_orchestrator as lab

def sample(tmp_path, monkeypatch, executed=True):
    archive = tmp_path / "synthetic.zip"
    archive.write_bytes(b"synthetic only")
    source = hashlib.sha256(b"synthetic only").hexdigest()
    commit = "b" * 40
    job = {"id": "synthetic-ema", "strategy": "ema", "timeframe": "M15",
           "execution": "fast", "start": "2024-01-01", "end": "2024-02-29",
           "parameters": {"fast": 9, "slow": 21}}
    plan = {"schema": lab.SCHEMA, "dataset": str(archive),
            "source_sha256": source, "engine_commit": commit,
            "exposure_context": "historical_exposed", "jobs": [job], "grids": []}
    _, digest = lab.expand(plan)
    record = {"status": lab.PASSED, "trades": 4, "net_pnl": 1.0,
              "total_cost": 1.6, "positive_months": 1, "months_observed": 2,
              "monthly_net_pnl": {"2024-01": 3.0, "2024-02": -2.0},
              "summary_sha256": "c" * 64, "monthly_sha256": "d" * 64,
              "weekly_sha256": "e" * 64, "trades_sha256": "f" * 64}
    manifest = {"schema": lab.SCHEMA, "plan_sha256": digest,
                "source_sha256": source, "engine_commit": commit,
                "results": {"synthetic-ema": record} if executed else {}}
    out = tmp_path / "out"
    out.mkdir()
    (out / "batch_manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(lab, "checkout_commit", lambda: commit)
    monkeypatch.setattr(lab, "audit_run", lambda *a: record)
    monkeypatch.setattr(lab, "file_sha",
                        lambda p: source if Path(p) == archive else "d" * 64)
    monkeypatch.setattr(lab, "read_ledger_csv", lambda p: [
        {"period": "2024-01", "trades": "4", "total_cost": "1.6",
         "observed_m1_samples": "123"},
        {"period": "2024-02", "trades": "0", "total_cost": "0",
         "observed_m1_samples": "111"}])
    return plan, out, manifest, record

def test_monthly_worst_sample_fee_and_nonapproval(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch)
    report = score.scorecard(plan, out)
    item = report["jobs"][0]
    assert (item["worst_month_utc"], item["worst_month_net_usd_per_oz"]) == ("2024-02", -2)
    assert item["positive_months"] == 1 and item["zero_trade_months"] == 1
    assert item["monthly"][0]["observed_m1_samples"] == 123
    assert item["all_in_fees_usd_per_oz"] == 1.6
    assert item["observed_m1_floating_drawdown_usd_per_oz"] is None
    assert not item["shared_capacity_verified"] and not item["clean_prospective_oos"]
    assert report["approved_strategies"] == 0

def test_unexecuted_not_counted(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch, executed=False)
    report = score.scorecard(plan, out)
    assert report["not_executed_jobs"] == 1 and report["jobs"] == []

def test_missing_source_rejected(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch)
    Path(plan["dataset"]).unlink()
    with pytest.raises(ValueError, match="missing"):
        score.scorecard(plan, out)

def test_stale_checkout_rejected(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch)
    monkeypatch.setattr(lab, "checkout_commit", lambda: "0" * 40)
    with pytest.raises(ValueError, match="revision"):
        score.scorecard(plan, out)

def test_unknown_job_rejected(tmp_path, monkeypatch):
    plan, out, manifest, record = sample(tmp_path, monkeypatch)
    manifest["results"]["unknown"] = record
    (out / "batch_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Unknown"):
        score.scorecard(plan, out)

def test_tampered_record_rejected(tmp_path, monkeypatch):
    plan, out, manifest, record = sample(tmp_path, monkeypatch)
    original = dict(record)  # keep the canonical fixture independent of the tampered manifest
    monkeypatch.setattr(lab, "audit_run", lambda *a: original)
    manifest["results"]["synthetic-ema"]["net_pnl"] = 999
    (out / "batch_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="differs"):
        score.scorecard(plan, out)

def test_failed_record_rejected(tmp_path, monkeypatch):
    plan, out, manifest, _ = sample(tmp_path, monkeypatch)
    manifest["results"]["synthetic-ema"] = {"status": "FAILED"}
    (out / "batch_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Failed"):
        score.scorecard(plan, out)

def test_duplicate_json_keys_rejected(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch)
    (out / "batch_manifest.json").write_text('{"schema":"x","schema":"x"}')
    with pytest.raises(ValueError, match="Duplicate"):
        score.scorecard(plan, out)

def test_symlinked_output_rejected(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch)
    link = tmp_path / "link"
    link.symlink_to(out, target_is_directory=True)
    with pytest.raises(ValueError, match="Unsafe"):
        score.scorecard(plan, link)

def test_negative_monthly_trades_rejected(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch)
    monkeypatch.setattr(lab, "read_ledger_csv", lambda p: [
        {"period": "2024-01", "trades": "-1", "total_cost": "0", "observed_m1_samples": "1"},
        {"period": "2024-02", "trades": "0", "total_cost": "0", "observed_m1_samples": "1"}])
    with pytest.raises(ValueError, match="integer"):
        score.scorecard(plan, out)

def test_wrong_month_order_rejected(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch)
    monkeypatch.setattr(lab, "read_ledger_csv", lambda p: [
        {"period": "2024-02"}, {"period": "2024-01"}])
    with pytest.raises(ValueError, match="ordering"):
        score.scorecard(plan, out)

def test_no_files_written(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch, executed=False)
    before = sorted(p.relative_to(out) for p in out.rglob("*"))
    score.scorecard(plan, out)
    assert sorted(p.relative_to(out) for p in out.rglob("*")) == before
