"""Synthetic-only regression tests for training-only candidate screens."""
from __future__ import annotations

import copy
import pytest
from scripts import research_candidate_screen as screen


def setup(monkeypatch):
    names = ("alpha", "beta")
    jobs = [{"id": name, "spec": {"strategy": "ema", "parameters": {"fast": 8 + i}}}
            for i, name in enumerate(names)]
    a = {"2024-01": 4., "2024-02": 2., "2024-03": 3.,
         "2024-04": -100., "2024-05": -100., "2024-06": -100.}
    b = {"2024-01": 1., "2024-02": 2., "2024-03": 2.,
         "2024-04": 100., "2024-05": 100., "2024-06": 100.}
    records = {"alpha": {"status": "OK", "monthly_net_pnl": a, "monthly_sha256": "sha"},
               "beta": {"status": "OK", "monthly_net_pnl": b, "monthly_sha256": "sha"}}
    plan = {"source_sha256": "a" * 64, "engine_commit": "b" * 40}
    manifest = {"schema": "TEST_BATCH", "plan_sha256": "plan-hash",
                "source_sha256": plan["source_sha256"],
                "engine_commit": plan["engine_commit"], "results": records}
    monkeypatch.setattr(screen.batch, "SCHEMA", "TEST_BATCH")
    monkeypatch.setattr(screen.batch, "PASSED", "OK")
    monkeypatch.setattr(screen.batch, "expand", lambda _: (jobs, "plan-hash"))
    monkeypatch.setattr(screen.batch, "audit_run", lambda folder, *_: records[folder.name].copy())
    monkeypatch.setattr(screen.batch, "read_ledger_csv", lambda folder: [
        {"period": m, "trades": "10"} for m in records[folder.parent.name]["monthly_net_pnl"]])
    monkeypatch.setattr(screen.batch, "file_sha", lambda _: "sha")
    monkeypatch.setattr(screen.batch, "count", lambda x: int(x))
    monkeypatch.setattr(screen.batch, "canonical", lambda x: repr(sorted(x.items())).encode())
    opts = {"train_start": "2024-01", "train_end": "2024-03",
            "review_start": "2024-04", "review_end": "2024-06"}
    return plan, manifest, records, opts


def test_later_review_cannot_change_training_rank_or_eligibility(monkeypatch, tmp_path):
    plan, manifest, records, opts = setup(monkeypatch)
    original = screen.select(plan, manifest, tmp_path, **opts)
    assert [x["job_id"] for x in original["results"]] == ["alpha", "beta"]
    assert original["results"][0]["later_review_descriptive_only"]["net_pnl_usd_per_oz"] == -300
    assert original["results"][1]["later_review_descriptive_only"]["net_pnl_usd_per_oz"] == 300
    for rec in records.values():
        for m in ("2024-04", "2024-05", "2024-06"):
            rec["monthly_net_pnl"][m] *= -10
    altered = screen.select(plan, manifest, tmp_path, **opts)
    for before, after in zip(original["results"], altered["results"]):
        assert (before["job_id"], before["training_rank"], before["train"],
                before["training_screen"]) == (
                after["job_id"], after["training_rank"], after["train"],
                after["training_screen"])


def test_training_minimum_trade_gate(monkeypatch, tmp_path):
    plan, manifest, _, opts = setup(monkeypatch)
    out = screen.select(plan, manifest, tmp_path, min_train_trades=40, **opts)
    assert all(x["training_screen"] == "REJECTED_EXPLORATORY" for x in out["results"])


def test_rejects_train_review_overlap(monkeypatch, tmp_path):
    plan, manifest, _, opts = setup(monkeypatch)
    opts["review_start"] = "2024-03"
    with pytest.raises(ValueError, match="overlap"):
        screen.select(plan, manifest, tmp_path, **opts)


def test_minimum_window_months(monkeypatch, tmp_path):
    plan, manifest, _, opts = setup(monkeypatch)
    opts["train_end"] = "2024-02"
    with pytest.raises(ValueError, match="three months"):
        screen.select(plan, manifest, tmp_path, **opts)


@pytest.mark.parametrize("start,end", [
    ("2024-00", "2024-12"), ("2024-01", "2024-13"),
    ("2024-1", "2024-12"), ("2025-01", "2024-12"),
    (None, "2024-12"), ("2024-02-01", "2024-12"),
])
def test_bad_calendar_windows(start, end):
    with pytest.raises(ValueError):
        screen.months_between(start, end)


def test_month_end_drawdown_from_zero_baseline():
    assert screen.drawdown([-5, 10, -3, -9, 20]) == 12
    assert screen.drawdown([1, 2, 3]) == 0
    assert screen.drawdown([-1, -2, -3]) == 6
    with pytest.raises(ValueError):
        screen.drawdown([float("nan")])


def test_unknown_manifest_job_fails_closed(monkeypatch, tmp_path):
    plan, manifest, _, opts = setup(monkeypatch)
    manifest["results"]["intruder"] = {"status": "OK"}
    with pytest.raises(ValueError, match="Unknown"):
        screen.select(plan, manifest, tmp_path, **opts)


def test_failed_run_fails_closed(monkeypatch, tmp_path):
    plan, manifest, _, opts = setup(monkeypatch)
    manifest["results"]["alpha"]["status"] = "FAILED_REQUIRES_INVESTIGATION"
    with pytest.raises(ValueError, match="failed"):
        screen.select(plan, manifest, tmp_path, **opts)


def test_tampered_manifest_fails_closed(monkeypatch, tmp_path):
    plan, manifest, records, opts = setup(monkeypatch)
    snapshot = copy.deepcopy(records)
    monkeypatch.setattr(screen.batch, "audit_run", lambda folder, *_: snapshot[folder.name])
    manifest["results"]["alpha"]["monthly_net_pnl"]["2024-01"] += 1
    with pytest.raises(ValueError, match="disagree"):
        screen.select(plan, manifest, tmp_path, **opts)


def test_missing_month_not_silently_compared(monkeypatch, tmp_path):
    plan, manifest, records, opts = setup(monkeypatch)
    records["beta"]["monthly_net_pnl"].pop("2024-06")
    out = screen.select(plan, manifest, tmp_path, **opts)
    assert out["compared_jobs"] == 1
    assert out["noncomparable_job_ids"] == ["beta"]


def test_empty_manifest_is_not_success(monkeypatch, tmp_path):
    plan, manifest, _, opts = setup(monkeypatch)
    manifest["results"].clear()
    with pytest.raises(ValueError, match="No comparable"):
        screen.select(plan, manifest, tmp_path, **opts)


def test_pending_jobs_are_not_audited(monkeypatch, tmp_path):
    plan, manifest, _, opts = setup(monkeypatch)
    manifest["results"].pop("beta")
    out = screen.select(plan, manifest, tmp_path, **opts)
    assert (out["defined_jobs"], out["audited_jobs"], out["compared_jobs"]) == (2, 1, 1)


@pytest.mark.parametrize("invalid", [0, True, 1.1, -1, float("nan")])
def test_invalid_positive_month_threshold(monkeypatch, tmp_path, invalid):
    plan, manifest, _, opts = setup(monkeypatch)
    with pytest.raises(ValueError):
        screen.select(plan, manifest, tmp_path, min_positive_fraction=invalid, **opts)


@pytest.mark.parametrize("invalid", [0, True, -1, 1.2])
def test_invalid_trade_minimum(monkeypatch, tmp_path, invalid):
    plan, manifest, _, opts = setup(monkeypatch)
    with pytest.raises(ValueError):
        screen.select(plan, manifest, tmp_path, min_train_trades=invalid, **opts)


def test_html_escapes_untrusted_job_name_and_warns_no_oos():
    report = {"train_months": ["2024-01", "2024-03"],
              "later_review_months": ["2024-04", "2024-06"],
              "results": [{"training_rank": 1, "job_id": "<script>alert(1)</script>",
                           "strategy": "ema", "training_screen": "PASSED_EXPLORATORY",
                           "train": {"trades": 30, "positive_month_fraction": 1.0,
                                     "net_pnl_usd_per_oz": 9.,
                                     "max_month_end_drawdown_usd_per_oz": 0.},
                           "later_review_descriptive_only": {
                               "net_pnl_usd_per_oz": -1.,
                               "positive_month_fraction": 0.2}}]}
    html = screen.render(report)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "NOT independent OOS" in html


def test_partial_manifest_cannot_issue_exploratory_eligibility_or_rank(monkeypatch, tmp_path):
    plan, manifest, _, opts = setup(monkeypatch)
    manifest["results"].pop("beta")
    result = screen.select(plan, manifest, tmp_path, **opts)
    assert result["research_status"] == "INCOMPLETE_SEARCH_UNIVERSE"
    assert result["unexecuted_job_ids"] == ["beta"]
    assert result["compared_jobs"] == 1
    assert result["results"][0]["training_rank"] is None
    assert result["results"][0]["training_screen"] == "NOT_ELIGIBLE_BATCH_INCOMPLETE"
    assert "no eligibility or ranks" in screen.render(result)


def test_noncomparable_completed_job_blocks_training_promotion(monkeypatch, tmp_path):
    plan, manifest, records, opts = setup(monkeypatch)
    records["beta"]["monthly_net_pnl"].pop("2024-06")
    result = screen.select(plan, manifest, tmp_path, **opts)
    assert result["research_status"] == "INCOMPLETE_SEARCH_UNIVERSE"
    assert result["unexecuted_job_ids"] == []
    assert result["noncomparable_job_ids"] == ["beta"]
    assert result["results"][0]["training_rank"] is None
    assert result["results"][0]["training_screen"] == "NOT_ELIGIBLE_BATCH_INCOMPLETE"


def test_complete_search_universe_preserves_training_only_eligibility(monkeypatch, tmp_path):
    plan, manifest, _, opts = setup(monkeypatch)
    result = screen.select(plan, manifest, tmp_path, **opts)
    assert result["research_status"] == "HISTORICAL_EXPOSED_SCREEN_COMPLETE"
    assert result["unexecuted_job_ids"] == []
    assert result["noncomparable_job_ids"] == []
    assert result["results"][0]["training_rank"] == 1
    assert result["results"][0]["training_screen"] == "PASSED_EXPLORATORY"


def test_monthly_downside_inactivity_and_nonpositive_streak():
    months = screen.months_between("2024-01", "2024-06")
    pnl = dict(zip(months, [10., -3., -5., 0., 2., -1.]))
    trades = dict(zip(months, [2, 1, 1, 0, 2, 1]))
    result = screen.metrics(months, pnl, trades)
    assert result["worst_month_utc"] == "2024-03"
    assert result["worst_month_usd_per_oz"] == -5.
    assert result["worst_rolling_3m_net_usd_per_oz"] == -8.
    assert result["longest_nonpositive_month_streak"] == 3
    assert result["zero_trade_months"] == 1
    assert result["max_month_end_drawdown_usd_per_oz"] == 8.


def test_candidate_screen_renders_downside_but_not_floating_m1(monkeypatch, tmp_path):
    plan, manifest, _, opts = setup(monkeypatch)
    html = screen.render(screen.select(plan, manifest, tmp_path, **opts))
    for label in ("Train worst month/oz", "Train worst 3m/oz",
                  "Train zero-trade months", "Train longest nonpositive streak",
                  "Train month-end DD/oz"):
        assert label in html
    assert "NOT independent OOS" in html
    assert "floating M1 DD" not in html


def test_downside_rejects_nonfinite_and_missing_months():
    months = screen.months_between("2024-01", "2024-03")
    with pytest.raises(ValueError, match="Invalid monthly"):
        screen.metrics(months, dict(zip(months, [1., float("inf"), -1.])),
                       dict.fromkeys(months, 1))
    with pytest.raises(ValueError, match="Missing comparison"):
        screen.metrics(months, {"2024-01": 1., "2024-02": 2.},
                       dict.fromkeys(months, 1))
