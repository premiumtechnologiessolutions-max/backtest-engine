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

def test_monthly_downside_full_calendar_streak_and_tail():
    months = [
        {"month_utc": f"2024-{i:02d}", "net_usd_per_oz": value, "trades": trades}
        for i, (value, trades) in enumerate(
            [(-1, 2), (-2, 3), (-3, 4), (10, 1), (-5, 1), (-6, 0)], 1)
    ]
    risk = score.monthly_downside(months, "2024-01-01", "2024-06-30")
    assert risk["nonpositive_months"] == 5
    assert risk["months_with_trades"] == 5
    assert risk["longest_nonpositive_observed_month_streak"] == 3
    assert risk["worst_three_complete_calendar_months_net_usd_per_oz"] == -6
    assert risk["worst_three_complete_calendar_months_window_utc"] == ["2024-01", "2024-03"]
    assert risk["partial_requested_calendar_months_utc"] == []


def test_monthly_downside_partial_edges_not_claimed_as_three_full_months():
    months = [
        {"month_utc": f"2024-{i:02d}", "net_usd_per_oz": -1, "trades": 1}
        for i in range(1, 5)
    ]
    risk = score.monthly_downside(months, "2024-01-15", "2024-04-15")
    assert risk["partial_requested_calendar_months_utc"] == ["2024-01", "2024-04"]
    assert risk["worst_three_complete_calendar_months_net_usd_per_oz"] is None
    assert risk["worst_three_complete_calendar_months_window_utc"] is None
    assert risk["longest_nonpositive_observed_month_streak"] == 4


def test_monthly_downside_leap_day_full_month_and_tie_break():
    months = [
        {"month_utc": f"2024-{i:02d}", "net_usd_per_oz": -1, "trades": 1}
        for i in range(1, 5)
    ]
    risk = score.monthly_downside(months, "2024-01-01", "2024-04-30")
    assert risk["partial_requested_calendar_months_utc"] == []
    assert risk["worst_three_complete_calendar_months_net_usd_per_oz"] == -3
    assert risk["worst_three_complete_calendar_months_window_utc"] == ["2024-01", "2024-03"]


def test_monthly_downside_calendar_gap_breaks_streak_and_rolling_window():
    months = [
        {"month_utc": month, "net_usd_per_oz": -1, "trades": 1}
        for month in ("2024-01", "2024-03", "2024-04")
    ]
    risk = score.monthly_downside(months, "2024-01-01", "2024-04-30")
    assert risk["longest_nonpositive_observed_month_streak"] == 2
    assert risk["worst_three_complete_calendar_months_net_usd_per_oz"] is None


@pytest.mark.parametrize("months,start,end", [
    ([{"month_utc": "2024-00", "net_usd_per_oz": 1, "trades": 1}], "2024-01-01", "2024-12-31"),
    ([{"month_utc": "2024-01", "net_usd_per_oz": float("nan"), "trades": 1}], "2024-01-01", "2024-12-31"),
    ([{"month_utc": "2024-01", "net_usd_per_oz": 1, "trades": True}], "2024-01-01", "2024-12-31"),
    ([{"month_utc": "2024-01", "net_usd_per_oz": 1, "trades": 1},
      {"month_utc": "2024-01", "net_usd_per_oz": 1, "trades": 1}], "2024-01-01", "2024-12-31"),
    ([{"month_utc": "2024-01", "net_usd_per_oz": 1, "trades": 1}], "2024-02-01", "2024-02-29"),
    ([], "2024-01-01", "2024-01-31"),
])
def test_monthly_downside_rejects_unsafe_evidence(months, start, end):
    with pytest.raises(ValueError):
        score.monthly_downside(months, start, end)


def test_monthly_scorecard_includes_downside_metrics(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch)
    result = score.scorecard(plan, out)["jobs"][0]
    assert result["nonpositive_months"] == 1
    assert result["longest_nonpositive_observed_month_streak"] == 1
    assert result["worst_three_complete_calendar_months_net_usd_per_oz"] is None
    assert result["partial_requested_calendar_months_utc"] == []


def frozen_pins(plan, record):
    _, digest = lab.expand(plan)
    return {
        "schema": "NRFX_EQUITY_PINS_V1",
        "plan_sha256": digest,
        "source_sha256": plan["source_sha256"],
        "engine_commit": plan["engine_commit"],
        "jobs": {"synthetic-ema": {
            "summary.json": record["summary_sha256"],
            "monthly.csv": record["monthly_sha256"],
            "equity_m1.csv": "a" * 64,
        }},
    }


def fake_equity_result():
    return {
        "max_observed_m1_global_peak_drawdown_usd_per_oz": 4.5,
        "monthly": [
            {"month_utc": "2024-01", "observed_m1_samples": 123,
             "max_observed_m1_global_peak_drawdown_usd_per_oz": 2.5,
             "observed_gap_events_from_prior_mark": 3},
            {"month_utc": "2024-02", "observed_m1_samples": 111,
             "max_observed_m1_global_peak_drawdown_usd_per_oz": 4.5,
             "observed_gap_events_from_prior_mark": 1},
        ],
    }


def test_hash_pinned_m1_months_join_only_after_independent_audit(tmp_path, monkeypatch):
    plan, out, _, record = sample(tmp_path, monkeypatch)
    pins = frozen_pins(plan, record)
    calls = []
    def verifier(folder, archive, source, engine, hashes):
        calls.append((folder, archive, source, engine, hashes))
        return fake_equity_result()
    monkeypatch.setattr(score.equity_audit, "audit_equity", verifier)
    report = score.scorecard(plan, out, equity_pins=pins)
    job = report["jobs"][0]
    assert len(calls) == 1
    assert calls[0][4] == pins["jobs"]["synthetic-ema"]
    assert job["observed_m1_floating_drawdown_usd_per_oz"] == 4.5
    assert [m["max_observed_m1_global_peak_drawdown_usd_per_oz"]
            for m in job["monthly"]] == [2.5, 4.5]
    assert [m["observed_m1_gap_events_from_prior_mark"]
            for m in job["monthly"]] == [3, 1]
    assert job["evidence_sha256"]["equity_m1_sha256"] == "a" * 64
    assert report["hash_pinned_m1_jobs"] == 1
    assert report["unverified_floating_m1_jobs"] == 0
    assert report["approved_strategies"] == 0


def test_missing_pins_remain_explicit_na_per_month(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch)
    report = score.scorecard(plan, out)
    assert report["hash_pinned_m1_jobs"] == 0
    assert report["unverified_floating_m1_jobs"] == 1
    assert all(month["max_observed_m1_global_peak_drawdown_usd_per_oz"] is None
               for month in report["jobs"][0]["monthly"])
    assert "equity_m1_sha256" not in report["jobs"][0]["evidence_sha256"]


@pytest.mark.parametrize("mutation", ["bad-schema", "bad-plan", "bad-source",
                                       "bad-engine", "bad-hash", "bad-summary",
                                       "unknown-job"])
def test_equity_pins_fail_closed_on_stale_or_untrusted_evidence(
        tmp_path, monkeypatch, mutation):
    plan, out, _, record = sample(tmp_path, monkeypatch)
    pins = frozen_pins(plan, record)
    if mutation == "bad-schema":
        pins["schema"] = "NOT_FROZEN"
    elif mutation == "bad-plan":
        pins["plan_sha256"] = "0" * 64
    elif mutation == "bad-source":
        pins["source_sha256"] = "0" * 64
    elif mutation == "bad-engine":
        pins["engine_commit"] = "0" * 40
    elif mutation == "bad-hash":
        pins["jobs"]["synthetic-ema"]["equity_m1.csv"] = "invalid"
    elif mutation == "bad-summary":
        pins["jobs"]["synthetic-ema"]["summary.json"] = "0" * 64
    else:
        pins["jobs"]["not-executed"] = pins["jobs"].pop("synthetic-ema")
    with pytest.raises(ValueError):
        score.scorecard(plan, out, equity_pins=pins)


@pytest.mark.parametrize("mutation", ["wrong-month", "wrong-samples", "missing-month"])
def test_equity_audit_must_reconcile_exact_months_and_samples(
        tmp_path, monkeypatch, mutation):
    plan, out, _, record = sample(tmp_path, monkeypatch)
    result = fake_equity_result()
    if mutation == "wrong-month":
        result["monthly"][1]["month_utc"] = "2024-03"
    elif mutation == "wrong-samples":
        result["monthly"][0]["observed_m1_samples"] = 124
    else:
        result["monthly"].pop()
    monkeypatch.setattr(score.equity_audit, "audit_equity", lambda *args: result)
    with pytest.raises(ValueError, match="month|sample"):
        score.scorecard(plan, out, equity_pins=frozen_pins(plan, record))


def test_pin_to_unexecuted_job_rejected_without_inventing_months(tmp_path, monkeypatch):
    plan, out, _, record = sample(tmp_path, monkeypatch, executed=False)
    with pytest.raises(ValueError, match="unexecuted"):
        score.scorecard(plan, out, equity_pins=frozen_pins(plan, record))


def test_equity_audit_failure_is_not_silently_downgraded_to_na(tmp_path, monkeypatch):
    plan, out, _, record = sample(tmp_path, monkeypatch)
    def reject(*args):
        raise ValueError("Frozen evidence SHA mismatch")
    monkeypatch.setattr(score.equity_audit, "audit_equity", reject)
    with pytest.raises(ValueError, match="SHA mismatch"):
        score.scorecard(plan, out, equity_pins=frozen_pins(plan, record))


def test_monthly_downside_reports_missing_requested_utc_months():
    months = [
        {"month_utc": "2023-12", "net_usd_per_oz": -1, "trades": 1},
        {"month_utc": "2024-02", "net_usd_per_oz": 2, "trades": 1},
    ]
    result = score.monthly_downside(months, "2023-12-01", "2024-02-29")
    assert result["missing_requested_calendar_months_utc"] == ["2024-01"]
    assert result["requested_calendar_month_coverage_complete"] is False
    assert result["worst_three_complete_calendar_months_net_usd_per_oz"] is None


def test_monthly_downside_full_coverage_includes_partial_edge_months():
    months = [
        {"month_utc": "2024-01", "net_usd_per_oz": 1, "trades": 1},
        {"month_utc": "2024-02", "net_usd_per_oz": -2, "trades": 1},
    ]
    result = score.monthly_downside(months, "2024-01-15", "2024-02-15")
    assert result["requested_calendar_month_coverage_complete"] is True
    assert result["missing_requested_calendar_months_utc"] == []
    assert result["partial_requested_calendar_months_utc"] == ["2024-01", "2024-02"]


def test_canonical_scorecard_rejects_missing_requested_month(tmp_path, monkeypatch):
    plan, out, manifest, _ = sample(tmp_path, monkeypatch)
    plan["jobs"][0]["end"] = "2024-03-31"
    _, digest = lab.expand(plan)
    manifest["plan_sha256"] = digest
    (out / "batch_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="missing requested UTC calendar months"):
        score.scorecard(plan, out)


def test_canonical_scorecard_marks_complete_utc_month_coverage(tmp_path, monkeypatch):
    plan, out, _, _ = sample(tmp_path, monkeypatch)
    result = score.scorecard(plan, out)["jobs"][0]
    assert result["requested_calendar_month_coverage_complete"] is True
    assert result["missing_requested_calendar_months_utc"] == []


def test_monthly_downside_rejects_unbounded_month_window():
    with pytest.raises(ValueError, match="361 calendar months"):
        score.monthly_downside(
            [{"month_utc": "2024-01", "net_usd_per_oz": 1, "trades": 1}],
            "1980-01-01", "2024-12-31",
        )


def test_complete_month_risk_does_not_certify_partial_edge_losses():
    rows = [
        {"month_utc": "2024-01", "net_usd_per_oz": -99, "trades": 1},
        {"month_utc": "2024-02", "net_usd_per_oz": -2, "trades": 2},
        {"month_utc": "2024-03", "net_usd_per_oz": -3, "trades": 3},
        {"month_utc": "2024-04", "net_usd_per_oz": -100, "trades": 4},
    ]
    risk = score.monthly_downside(rows, "2024-01-15", "2024-04-15")
    assert risk["complete_calendar_months_observed"] == 2
    assert risk["complete_nonpositive_calendar_months"] == 2
    assert risk["longest_nonpositive_complete_calendar_month_streak"] == 2
    assert risk["longest_nonpositive_observed_month_streak"] == 4
    assert risk["worst_complete_calendar_month_utc"] == "2024-03"
    assert risk["worst_complete_calendar_month_net_usd_per_oz"] == -3
    assert risk["worst_three_complete_calendar_months_trade_count"] is None


def test_complete_month_downside_window_reports_observed_trade_support():
    rows = [
        {"month_utc": month, "net_usd_per_oz": net, "trades": trades}
        for month, net, trades in [
            ("2024-01", -1, 4), ("2024-02", -2, 0),
            ("2024-03", -3, 6), ("2024-04", 10, 8),
        ]
    ]
    risk = score.monthly_downside(rows, "2024-01-01", "2024-04-30")
    assert risk["worst_three_complete_calendar_months_window_utc"] == ["2024-01", "2024-03"]
    assert risk["worst_three_complete_calendar_months_trade_count"] == 10
    assert risk["complete_calendar_months_observed"] == 4
    assert risk["complete_nonpositive_calendar_months"] == 3


def test_missing_month_breaks_complete_loss_streak():
    rows = [
        {"month_utc": "2024-01", "net_usd_per_oz": -1, "trades": 1},
        {"month_utc": "2024-03", "net_usd_per_oz": -1, "trades": 1},
        {"month_utc": "2024-04", "net_usd_per_oz": -1, "trades": 1},
    ]
    risk = score.monthly_downside(rows, "2024-01-01", "2024-04-30")
    assert risk["longest_nonpositive_complete_calendar_month_streak"] == 2
    assert risk["requested_calendar_month_coverage_complete"] is False
    assert risk["worst_three_complete_calendar_months_trade_count"] is None


def test_complete_worst_month_ties_keep_earliest_utc_month():
    rows = [
        {"month_utc": "2024-01", "net_usd_per_oz": -2, "trades": 0},
        {"month_utc": "2024-02", "net_usd_per_oz": -2, "trades": 1},
    ]
    risk = score.monthly_downside(rows, "2024-01-01", "2024-02-29")
    assert risk["worst_complete_calendar_month_utc"] == "2024-01"
    assert risk["worst_complete_calendar_month_net_usd_per_oz"] == -2
