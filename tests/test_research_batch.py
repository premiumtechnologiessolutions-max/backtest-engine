"""Synthetic-only batch contract checks; never touches real market data."""
import csv
import json
from pathlib import Path
import subprocess

import pytest
from scripts import research_batch as rb


def frozen_plan(source):
    return {
        "schema": "NRFX_BATCH_V1", "source": str(source),
        "source_sha256": rb.fingerprint_file(source), "engine_commit": "a" * 40,
        "start": "2024-01-01", "end": "2024-02-29",
        "experiments": [
            {"id": "EMA_M15_A", "strategy": "ema", "timeframe": "M15",
             "execution": "reference", "parameters": {
                "fast": 9, "slow": 21, "stop_atr": 1.5, "rr": 2.0}},
            {"id": "DONCHIAN_H1_A", "strategy": "donchian", "timeframe": "H1",
             "execution": "fast", "parameters": {
                "donchian_lookback": 20, "stop_usd": 15, "target_usd": 30}},
        ],
    }


@pytest.fixture
def plan(tmp_path):
    source = tmp_path / "Gold data.zip"
    source.write_bytes(b"synthetic only; not actual gold prices")
    return frozen_plan(source)


def mock_report(destination: Path, plan: dict, spec: dict, *, bad=None):
    destination.mkdir(parents=True, exist_ok=True)
    summary = {
        "execution": "synthetic_same_reference_bid_ohlc_fixed_all_in_fee",
        "run_parameters": {
            "strategy": spec["strategy"], "timeframe": spec["timeframe"],
            "execution": spec["execution"], "ounces": 1.0,
            "all_in_cost_per_ounce": 0.40, **spec["parameters"],
        },
        "source_fingerprints": {
            "source_file_sha256": plan["source_sha256"],
            "git_revision_env": plan["engine_commit"],
        },
        "net_pnl": 10, "trades": 3, "months_observed": 2,
    }
    if bad == "fee":
        summary["run_parameters"]["all_in_cost_per_ounce"] = 0
    elif bad == "source":
        summary["source_fingerprints"]["source_file_sha256"] = "b" * 64
    elif bad == "net":
        summary["net_pnl"] = 11
    (destination / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    with (destination / "monthly.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "period", "net_pnl", "trades", "month_has_observed_m1",
            "uncertain_gap_trades", "synthetic_end_of_data_trades",
        ])
        writer.writeheader()
        writer.writerow({
            "period": "2024-01", "net_pnl": "15", "trades": "2",
            "month_has_observed_m1": "True", "uncertain_gap_trades": "0",
            "synthetic_end_of_data_trades": "0",
        })
        if bad != "missing_month":
            writer.writerow({
                "period": "2024-02", "net_pnl": "-5", "trades": "1",
                "month_has_observed_m1": "True", "uncertain_gap_trades": "1",
                "synthetic_end_of_data_trades": "1",
            })


def test_default_dry_run_never_executes_or_writes(monkeypatch, plan, tmp_path):
    def forbidden(*a, **kw):
        raise AssertionError("dry run unexpectedly executed subprocess")
    monkeypatch.setattr(rb.subprocess, "run", forbidden)
    out = tmp_path / "never-created"
    result = rb.execute_plan(plan, out)
    assert result["status"] == "PLAN_VALIDATED_ONLY_NO_BACKTEST_EXECUTED"
    assert len(result["commands"]) == 2
    assert not out.exists()
    assert "--all-in-cost-per-ounce" in result["commands"][0]


@pytest.mark.parametrize("change", [
    lambda p: p["experiments"][0]["parameters"].update(fast=True),
    lambda p: p["experiments"][0]["parameters"].update(rr=float("nan")),
    lambda p: p["experiments"][0]["parameters"].update(slow=8),
    lambda p: p["experiments"][0].update(id="../../secrets"),
    lambda p: p["experiments"][0].update(id="DONCHIAN_H1_A"),
    lambda p: p["experiments"][1].update(strategy="fvg"),
    lambda p: p["experiments"][0]["parameters"].update(fee=0),
    lambda p: p.update(engine_commit="main"),
    lambda p: p.update(source_sha256="invalid"),
    lambda p: p.update(end="2023-01-01"),
    lambda p: p.update(unexpected="unknown"),
])
def test_invalid_specs_fail_closed(change, plan):
    change(plan)
    with pytest.raises(rb.ResearchBatchError):
        rb.validate_plan(plan)


@pytest.mark.parametrize("bad", ["fee", "source", "net", "missing_month"])
def test_inconsistent_canonical_outputs_rejected(plan, tmp_path, bad):
    spec = plan["experiments"][0]
    directory = tmp_path / "synth"
    mock_report(directory, plan, spec, bad=bad)
    with pytest.raises(rb.ResearchBatchError):
        rb.parse_report(directory, plan, spec)


def test_audited_months_and_partial_month_filter(plan, tmp_path):
    spec = plan["experiments"][0]
    directory = tmp_path / "synth"
    mock_report(directory, plan, spec)
    good = rb.parse_report(directory, plan, spec)
    assert good["net_pnl_usd_per_oz"] == 10
    assert good["positive_full_observed_months"] == 1
    assert good["eligible_full_observed_months"] == 2
    plan["end"] = "2024-02-15"
    partial = rb.parse_report(directory, plan, spec)
    assert partial["months"][1]["full_requested_month"] is False
    assert partial["eligible_full_observed_months"] == 1


def test_bad_source_fails_before_checkout_or_execution(plan, tmp_path, monkeypatch):
    plan["source_sha256"] = "0" * 64
    monkeypatch.setattr(rb, "verify_checkout", lambda *a: (_ for _ in ()).throw(
        AssertionError("must not check out")))
    out = tmp_path / "never"
    with pytest.raises(rb.ResearchBatchError, match="SHA256 mismatch"):
        rb.execute_plan(plan, out, execute=True)
    assert not out.exists()


def test_execution_writes_reconciled_monthly_comparison(plan, tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "verify_checkout", lambda *a: None)
    def runner(command, **kwargs):
        destination = Path(command[command.index("--out") + 1])
        spec = next(s for s in plan["experiments"] if s["id"] == destination.name)
        mock_report(destination, plan, spec)
        assert kwargs["env"]["GITHUB_SHA"] == plan["engine_commit"]
        return subprocess.CompletedProcess(command, 0, "synthetic-ok", "")
    monkeypatch.setattr(rb.subprocess, "run", runner)
    out = tmp_path / "new"
    result = rb.execute_plan(plan, out, execute=True)
    assert result["status"] == "COMPLETE_CANONICAL_REPLAY_NOT_INDEPENDENT_OOS"
    with (out / "monthly_comparison.csv").open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 4
    assert rows[0]["net_pnl_usd_per_oz"] == "15.0"
    assert all("NOT_OOS" in row["status"] for row in result["experiments"])


def test_failed_execution_does_not_publish_comparison(plan, tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "verify_checkout", lambda *a: None)
    monkeypatch.setattr(rb.subprocess, "run", lambda cmd, **k:
                        subprocess.CompletedProcess(cmd, 1, "", "synthetic fail"))
    out = tmp_path / "failure"
    with pytest.raises(rb.ResearchBatchError):
        rb.execute_plan(plan, out, execute=True)
    assert not (out / "monthly_comparison.csv").exists()
    assert json.loads((out / "batch_manifest.json").read_text())["status"] == "FAILED_NO_RANKING_PUBLISHED"


def test_refuses_to_overwrite_existing_output(plan, tmp_path, monkeypatch):
    monkeypatch.setattr(rb, "verify_checkout", lambda *a: None)
    out = tmp_path / "existing"
    out.mkdir()
    (out / "important").write_text("preserve")
    with pytest.raises(rb.ResearchBatchError, match="already exists"):
        rb.execute_plan(plan, out, execute=True)
    assert (out / "important").read_text() == "preserve"
