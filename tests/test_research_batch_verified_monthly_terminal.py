"""Synthetic-only tests for source-reverified private monthly Quant Terminal."""
from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

from scripts import research_batch_verified_monthly_terminal as terminal
from scripts.research_batch_monthly_scorecard import monthly_downside


def verified_report(*, pinned: bool = False) -> dict:
    months = [
        {"month_utc": "2024-01", "net_usd_per_oz": 5.25, "trades": 2,
         "all_in_fees_usd_per_oz": 0.8, "observed_m1_samples": 120,
         "max_observed_m1_global_peak_drawdown_usd_per_oz": 1.25 if pinned else None,
         "month_local_max_observed_m1_close_drawdown_usd_per_oz": 1.0 if pinned else None,
         "observed_m1_gap_events_from_prior_mark": 2 if pinned else None},
        {"month_utc": "2024-02", "net_usd_per_oz": -7.0, "trades": 1,
         "all_in_fees_usd_per_oz": 0.4, "observed_m1_samples": 115,
         "max_observed_m1_global_peak_drawdown_usd_per_oz": 8.0 if pinned else None,
         "month_local_max_observed_m1_close_drawdown_usd_per_oz": 6.5 if pinned else None,
         "observed_m1_gap_events_from_prior_mark": 0 if pinned else None},
    ]
    data = {
        "status": "RE_AUDITED_HISTORICAL_STANDALONE_NOT_OOS_NOT_APPROVED",
        "source_sha256_verified_locally": True,
        "plan_sha256": "a" * 64,
        "defined_parameter_jobs": 2,
        "reconciled_executed_jobs": 1,
        "not_executed_jobs": 1,
        "independent_hypotheses": None,
        "shared_capacity_portfolio_net_usd_per_oz": None,
        "hash_pinned_m1_jobs": int(pinned),
        "unverified_floating_m1_jobs": int(not pinned),
        "prospective_months": 0,
        "approved_strategies": 0,
        "jobs": [{
            "id": "synthetic-ema",
            "status": "HISTORICAL_EXPOSED_STANDALONE_NOT_APPROVED",
            "trades": 3, "positive_months": 1, "months_observed": 2,
            "evaluation_start_utc": "2024-01-01", "evaluation_end_utc": "2024-02-29",
            "zero_trade_months": 0, "nonpositive_months": 1,
            "months_with_trades": 2,
            "longest_nonpositive_observed_month_streak": 1,
            "partial_requested_calendar_months_utc": [],
            "missing_requested_calendar_months_utc": [],
            "requested_calendar_month_coverage_complete": True,
            "worst_three_complete_calendar_months_net_usd_per_oz": None,
            "worst_three_complete_calendar_months_window_utc": None,
            "worst_month_utc": "2024-02", "worst_month_net_usd_per_oz": -7.0,
            "net_usd_per_oz": -1.75, "all_in_fees_usd_per_oz": 1.2,
            "observed_m1_floating_drawdown_usd_per_oz": 8.0 if pinned else None,
            "max_observed_m1_month_local_drawdown_usd_per_oz": 6.5 if pinned else None,
            "shared_capacity_verified": False, "clean_prospective_oos": False,
            "monthly": months,
        }],
    }
    data["jobs"][0].update(monthly_downside(
        months, data["jobs"][0]["evaluation_start_utc"],
        data["jobs"][0]["evaluation_end_utc"]))
    return data


def test_verified_monthly_net_fees_worst_and_na_are_rendered():
    html = terminal.render_verified_monthly_html(verified_report())
    assert "synthetic-ema" in html
    assert "2024-01" in html and "2024-02" in html
    assert "+5.25" in html and "-7.00" in html
    assert "-1.75" in html and "1.20" in html
    assert "N/A" in html
    assert "0 prospective months · 0 approved" in html
    assert "NOT a shared-capacity portfolio" in html
    assert "M1 risk pinned" in html
    assert "2024-02 · -7.00" in html
    assert "Nonpositive-month streak" in html
    assert "Worst 3 complete UTC months" in html
    assert "Partial UTC edge months" in html


def test_pinned_m1_drawdown_and_gaps_are_observed_not_inferred():
    html = terminal.render_verified_monthly_html(verified_report(pinned=True))
    assert "8.00" in html and "1.25" in html and "6.50" in html
    assert "M1 month-local close DD" in html
    assert "M1 gaps" in html and "M1 marks" in html
    assert "1 M1 risk pinned" in html


def test_private_offline_bilingual_mobile_and_keyboard_controls():
    html = terminal.render_verified_monthly_html(verified_report())
    for item in ('name="viewport"', 'id="lang"', 'aria-pressed="false"',
                 'dir="ltr"', 'lang="en"', 'data-ar="الأبحاث الشهرية المدقّقة"',
                 'id="jobFilter"', 'id="monthFilter"', 'aria-live="polite"',
                 'prefers', 'https://cdn.'):
        if item in ("prefers", "https://cdn."):
            assert item not in html
        else:
            assert item in html
    assert "default-src 'none'" in html
    assert "document.documentElement.dir=ar?" in html
    assert "innerHTML" not in html


@pytest.mark.parametrize("change", [
    lambda r: r.update(status="COMPLETED_APPROVED"),
    lambda r: r.update(source_sha256_verified_locally=False),
    lambda r: r.update(prospective_months=1),
    lambda r: r.update(approved_strategies=1),
    lambda r: r.update(shared_capacity_portfolio_net_usd_per_oz=12.5),
    lambda r: r.update(reconciled_executed_jobs=2),
    lambda r: r.update(hash_pinned_m1_jobs=1),
    lambda r: r["jobs"][0].update(clean_prospective_oos=True),
    lambda r: r["jobs"][0].update(shared_capacity_verified=True),
    lambda r: r["jobs"][0].update(worst_month_net_usd_per_oz=999),
    lambda r: r["jobs"][0].update(net_usd_per_oz=999),
    lambda r: r["jobs"][0].update(trades=9),
    lambda r: r["jobs"][0].update(evaluation_end_utc="2024-01-31"),
    lambda r: r["jobs"][0].update(zero_trade_months=1),
    lambda r: r["jobs"][0].update(nonpositive_months=0),
    lambda r: r["jobs"][0].update(months_with_trades=1),
    lambda r: r["jobs"][0].update(longest_nonpositive_observed_month_streak=2),
    lambda r: r["jobs"][0].update(worst_three_complete_calendar_months_net_usd_per_oz=12),
    lambda r: r["jobs"][0].update(partial_requested_calendar_months_utc=["2024-02"]),
    lambda r: r["jobs"][0].update(all_in_fees_usd_per_oz=0),
    lambda r: r["jobs"][0]["monthly"][0].update(net_usd_per_oz=float("nan")),
    lambda r: r["jobs"][0]["monthly"][0].update(trades=True),
    lambda r: r["jobs"][0]["monthly"][0].update(all_in_fees_usd_per_oz=0.5),
    lambda r: r["jobs"][0]["monthly"][0].update(observed_m1_samples=0),
    lambda r: r["jobs"][0]["monthly"][1].update(month_utc="2024-01"),
    lambda r: r["jobs"][0]["monthly"][0].update(
        max_observed_m1_global_peak_drawdown_usd_per_oz=4.0),
    lambda r: r["jobs"][0].update(id="<script>alert(1)</script>"),
])
def test_forged_or_inconsistent_reports_fail_closed(change):
    report = verified_report()
    change(report)
    with pytest.raises(ValueError):
        terminal.render_verified_monthly_html(report)


def test_empty_verified_batch_is_explicit_not_fabricated():
    report = verified_report()
    report.update(jobs=[], reconciled_executed_jobs=0,
                  not_executed_jobs=2, hash_pinned_m1_jobs=0,
                  unverified_floating_m1_jobs=0)
    html = terminal.render_verified_monthly_html(report)
    assert "No executed source-verified jobs" in html
    assert "<tbody id=\"monthlyRows\"></tbody>" in html


def test_cli_requires_fresh_reaudit_before_any_export(tmp_path, monkeypatch):
    plan = tmp_path / "plan.json"
    plan.write_text("{}")
    html = tmp_path / "private.html"
    monkeypatch.setattr(terminal.audit, "scorecard",
                        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("source mismatch")))
    with pytest.raises(ValueError, match="source mismatch"):
        terminal.main(["--plan", str(plan), "--batch-output", str(tmp_path),
                       "--html", str(html)])
    assert not html.exists()


def test_cli_writes_private_html_only_after_audit(tmp_path, monkeypatch):
    plan = tmp_path / "plan.json"
    plan.write_text("{}")
    html = tmp_path / "private.html"
    monkeypatch.setattr(terminal.audit, "scorecard", lambda *a, **k: verified_report())
    assert terminal.main(["--plan", str(plan), "--batch-output", str(tmp_path),
                          "--html", str(html)]) == 0
    assert "synthetic-ema" in html.read_text()
    if os.name == "posix":
        assert html.stat().st_mode & 0o077 == 0


def test_cli_does_not_accept_unverified_precomputed_scorecard_json():
    with pytest.raises(SystemExit) as exc:
        terminal.main(["--scorecard-json", "/tmp/untrusted.json"])
    assert exc.value.code == 2

def test_pinned_global_peak_must_equal_max_monthly_risk():
    report = verified_report(pinned=True)
    report["jobs"][0]["observed_m1_floating_drawdown_usd_per_oz"] = 1.25
    with pytest.raises(ValueError, match="monthly maximum"):
        terminal.render_verified_monthly_html(report)


def test_three_complete_month_downside_is_recomputed_and_visible():
    report = verified_report()
    job = report["jobs"][0]
    job["monthly"].append({
        "month_utc": "2024-03", "net_usd_per_oz": -2.0, "trades": 0,
        "all_in_fees_usd_per_oz": 0.0, "observed_m1_samples": 118,
        "max_observed_m1_global_peak_drawdown_usd_per_oz": None,
        "observed_m1_gap_events_from_prior_mark": None,
    })
    job.update(
        evaluation_end_utc="2024-03-31", months_observed=3, zero_trade_months=1,
        nonpositive_months=2, months_with_trades=2,
        longest_nonpositive_observed_month_streak=2,
        worst_three_complete_calendar_months_net_usd_per_oz=-3.75,
        worst_three_complete_calendar_months_window_utc=["2024-01", "2024-03"],
        net_usd_per_oz=-3.75,
    )
    job.update(monthly_downside(job["monthly"], job["evaluation_start_utc"],
                                job["evaluation_end_utc"]))
    html = terminal.render_verified_monthly_html(report)
    assert "2024-01 → 2024-03 · -3.75" in html
    assert "Nonpositive-month streak" in html
    assert "Months with trades" in html
    job["worst_three_complete_calendar_months_net_usd_per_oz"] = -3.74
    with pytest.raises(ValueError, match="downside"):
        terminal.render_verified_monthly_html(report)


def test_partial_months_are_visible_but_not_three_complete_months():
    report = verified_report()
    job = report["jobs"][0]
    job["evaluation_start_utc"] = "2024-01-15"
    job["evaluation_end_utc"] = "2024-02-15"
    job.update(monthly_downside(job["monthly"], job["evaluation_start_utc"],
                                job["evaluation_end_utc"]))
    html = terminal.render_verified_monthly_html(report)
    assert "2024-01, 2024-02" in html
    assert "Worst 3 complete UTC months" in html
    assert "N/A" in html


def test_rejects_omitted_utc_month_even_when_totals_are_rebalanced():
    report = verified_report()
    job = report["jobs"][0]
    job["monthly"].pop()
    job.update(months_observed=1, trades=2, positive_months=1,
               net_usd_per_oz=5.25, all_in_fees_usd_per_oz=0.8,
               worst_month_utc="2024-01", worst_month_net_usd_per_oz=5.25)
    with pytest.raises(ValueError, match="coverage"):
        terminal.render_verified_monthly_html(report)



@pytest.mark.parametrize("tamper", [
    lambda r: r["jobs"][0]["monthly"][0].pop(
        "month_local_max_observed_m1_close_drawdown_usd_per_oz"),
    lambda r: r["jobs"][0]["monthly"][0].update(
        month_local_max_observed_m1_close_drawdown_usd_per_oz=True),
    lambda r: r["jobs"][0]["monthly"][1].update(
        month_local_max_observed_m1_close_drawdown_usd_per_oz=8.01),
    lambda r: r["jobs"][0].update(max_observed_m1_month_local_drawdown_usd_per_oz=6.4),
    lambda r: r["jobs"][0].update(max_observed_m1_month_local_drawdown_usd_per_oz=float("nan")),
])
def test_pinned_month_local_forgery_is_rejected(tamper):
    evidence = verified_report(pinned=True)
    tamper(evidence)
    with pytest.raises(ValueError):
        terminal.render_verified_monthly_html(evidence)


def test_unpinned_month_local_risk_is_never_accepted():
    evidence = verified_report()
    evidence["jobs"][0]["monthly"][0][
        "month_local_max_observed_m1_close_drawdown_usd_per_oz"] = 1.0
    with pytest.raises(ValueError):
        terminal.render_verified_monthly_html(evidence)


def test_unified_month_local_panel_reconciles_pinned_evidence():
    from scripts.research_terminal_verified_monthly_section import render_verified_monthly_section
    html = render_verified_monthly_section(verified_report(pinned=True))
    assert "Month-local observed M1 close DD" in html
    assert "M1 month-local close DD" in html
    assert "+6.50" in html
    assert "M1 global-peak DD" in html
