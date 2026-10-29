"""Synthetic regression tests for opt-in unified verified monthly Quant Terminal."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import research_terminal as main_terminal
from scripts.research_terminal_verified_monthly_section import render_verified_monthly_section
from scripts.research_terminal_ui import render_premium_html


def report():
    months = [
        {"month_utc": "2024-01", "net_usd_per_oz": 5.25, "trades": 2,
         "all_in_fees_usd_per_oz": 0.8, "observed_m1_samples": 120,
         "max_observed_m1_global_peak_drawdown_usd_per_oz": None,
         "observed_m1_gap_events_from_prior_mark": None},
        {"month_utc": "2024-02", "net_usd_per_oz": -7.0, "trades": 1,
         "all_in_fees_usd_per_oz": 0.4, "observed_m1_samples": 115,
         "max_observed_m1_global_peak_drawdown_usd_per_oz": None,
         "observed_m1_gap_events_from_prior_mark": None},
    ]
    return {
        "status": "RE_AUDITED_HISTORICAL_STANDALONE_NOT_OOS_NOT_APPROVED",
        "source_sha256_verified_locally": True, "plan_sha256": "a" * 64,
        "defined_parameter_jobs": 2, "reconciled_executed_jobs": 1,
        "not_executed_jobs": 1, "independent_hypotheses": None,
        "shared_capacity_portfolio_net_usd_per_oz": None,
        "hash_pinned_m1_jobs": 0, "unverified_floating_m1_jobs": 1,
        "prospective_months": 0, "approved_strategies": 0,
        "jobs": [{
            "id": "synthetic-ema", "status": "HISTORICAL_EXPOSED_STANDALONE_NOT_APPROVED",
            "trades": 3, "positive_months": 1, "months_observed": 2,
            "evaluation_start_utc": "2024-01-01", "evaluation_end_utc": "2024-02-29",
            "zero_trade_months": 0, "nonpositive_months": 1, "months_with_trades": 2,
            "longest_nonpositive_observed_month_streak": 1,
            "partial_requested_calendar_months_utc": [],
            "missing_requested_calendar_months_utc": [],
            "requested_calendar_month_coverage_complete": True,
            "worst_three_complete_calendar_months_net_usd_per_oz": None,
            "worst_three_complete_calendar_months_window_utc": None,
            "worst_month_utc": "2024-02", "worst_month_net_usd_per_oz": -7.0,
            "net_usd_per_oz": -1.75, "all_in_fees_usd_per_oz": 1.2,
            "observed_m1_floating_drawdown_usd_per_oz": None,
            "shared_capacity_verified": False, "clean_prospective_oos": False,
            "monthly": months,
        }],
    }


def model():
    return {
        "updated_utc": "2026-10-28T15:00:00Z",
        "research_status": "HISTORICALLY_EXPOSED_DESIGN_ONLY_NOT_OOS",
        "specifications": 0, "annual_replays": 0, "families": 0,
        "passing_24_of_24": 0, "fee": 0.4, "rows": [],
    }


def test_default_main_terminal_never_invents_monthly_returns():
    html = render_premium_html(model())
    assert "Verified monthly evidence not loaded" in html
    assert 'id="monthly"' in html
    assert "synthetic-ema" not in html


def test_verified_monthly_integrates_into_main_navigation_and_filters():
    data = model()
    data["verified_monthly"] = report()
    html = render_premium_html(data)
    assert 'data-view="monthly"' in html
    assert 'id="verifiedMonthRows"' in html
    assert 'id="verifiedJobFilter"' in html
    assert 'id="verifiedMonthFilter"' in html
    assert 'data-verified-month="2024-02"' in html
    assert "synthetic-ema" in html
    assert "+5.25" in html and "-7.00" in html
    assert "-1.75" in html and "N/A" in html
    assert "0 prospective months" in html
    assert "0 approved strategies" in html
    assert "No combined portfolio performance" in html
    assert "النتائج الشهرية" in html
    assert "https://cdn." not in html


@pytest.mark.parametrize("tamper", [
    lambda r: r.update(approved_strategies=1),
    lambda r: r.update(source_sha256_verified_locally=False),
    lambda r: r["jobs"][0].update(shared_capacity_verified=True),
    lambda r: r["jobs"][0].update(worst_month_net_usd_per_oz=900),
    lambda r: r["jobs"][0]["monthly"][0].update(all_in_fees_usd_per_oz=0.9),
    lambda r: r["jobs"][0]["monthly"][0].update(net_usd_per_oz=float("nan")),
    lambda r: r["jobs"][0].update(id="<img src=x onerror=alert(1)>"),
])
def test_forged_monthly_results_never_reach_main_terminal(tamper):
    data = model()
    data["verified_monthly"] = report()
    tamper(data["verified_monthly"])
    with pytest.raises(ValueError):
        render_premium_html(data)


def test_monthly_panel_bounded_against_massive_export():
    data = report()
    data["jobs"] = data["jobs"] * 21
    with pytest.raises(ValueError):
        render_verified_monthly_section(data)


def test_cli_reaudits_private_source_before_export(tmp_path, monkeypatch):
    from scripts import research_batch_monthly_scorecard as scorecard
    plan = tmp_path / "plan.json"
    plan.write_text("{}")
    registry = tmp_path / "registry.json"
    registry.write_text("{}")
    output = tmp_path / "terminal.html"
    monkeypatch.setattr(main_terminal, "dashboard_model", lambda *_: model())
    monkeypatch.setattr(scorecard, "scorecard",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("bad source")))
    with pytest.raises(ValueError, match="bad source"):
        main_terminal.main(["--registry", str(registry), "--out", str(output),
                            "--verified-monthly-plan", str(plan),
                            "--verified-monthly-output", str(tmp_path)])
    assert not output.exists()


def test_cli_renders_only_newly_reaudited_source(tmp_path, monkeypatch):
    from scripts import research_batch_monthly_scorecard as scorecard
    plan = tmp_path / "plan.json"
    plan.write_text("{}")
    registry = tmp_path / "registry.json"
    registry.write_text("{}")
    output = tmp_path / "terminal.html"
    monkeypatch.setattr(main_terminal, "dashboard_model", lambda *_: model())
    monkeypatch.setattr(scorecard, "scorecard", lambda *a, **k: report())
    assert main_terminal.main(["--registry", str(registry), "--out", str(output),
                               "--verified-monthly-plan", str(plan),
                               "--verified-monthly-output", str(tmp_path)]) == 0
    assert "synthetic-ema" in output.read_text()
    assert "-7.00" in output.read_text()


@pytest.mark.parametrize("args", [
    ["--verified-monthly-plan", "plan.json"],
    ["--verified-monthly-output", "runs"],
    ["--verified-monthly-equity-pins", "pins.json"],
])
def test_cli_rejects_incomplete_opt_in_arguments(args):
    with pytest.raises(SystemExit) as exc:
        main_terminal.main(args)
    assert exc.value.code == 2
