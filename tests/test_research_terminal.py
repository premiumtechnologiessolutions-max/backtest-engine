"""Fail-closed tests for the research-only static terminal."""
import pytest
from scripts.research_terminal import dashboard_model, render_html


def registry():
    return {
        "original_private_zip_sha256":
            "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121",
        "fixed_roundtrip_all_in_fee_usd_per_oz": 0.40,
        "research_status": "HISTORICALLY_EXPOSED_DESIGN_ONLY_NOT_OOS",
        "updated_utc": "2026-10-27T19:00:00Z",
        "completed_batches": [{
            "id": "NRF-FAC-001", "file": "scripts/batch_fixture.py",
            "family": "<script>alert(1)</script>",
            "years": [2012, 2013],
            "unique_parameter_specs": 2, "completed_annual_replays": 4,
            "active_annual_replays": 4,
            "maximum_positive_months_out_of_24": 23,
            "configs_annual_net_positive_both_years": 1,
            "configs_24_of_24": 0, "status": "REJECTED",
            "report": "docs/ONE.md",
        }],
        "feasibility_negative_controls": [],
        "totals": {
            "distinct_parameter_specs": 2, "yearly_backtests": 4,
            "exit_booked_monthly_points": 48,
            "independent_hypothesis_families": 1,
            "strictly_positive_every_month_in_both_years": 0,
            "zero_trade_parameter_specs_excluded": 0,
            "zero_trade_yearly_parameter_executions_excluded": 0,
            "total_yearly_parameter_executions_including_zero_trade_negative_control": 4,
        },
    }


def test_displays_explicitly_noncertified_research_and_escapes_html():
    model = dashboard_model(registry())
    assert model["passing_24_of_24"] == 0
    html = render_html(model)
    assert "not independently proven" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "Read evidence" in html
    assert "NO RISK FX / RESEARCH" in html


def test_inconsistent_registry_does_not_generate_dashboard():
    bad = registry()
    bad["totals"]["yearly_backtests"] += 1
    with pytest.raises(ValueError):
        dashboard_model(bad)


@pytest.mark.parametrize("malicious", [
    "javascript:alert(1)", "../../index.html", "docs/../../other",
    "https://attacker.test", "docs/<img>.md",
])
def test_unsafe_report_links_rejected(malicious):
    bad = registry()
    bad["completed_batches"][0]["report"] = malicious
    with pytest.raises(ValueError, match="Unsafe report"):
        dashboard_model(bad)


def test_boolean_replay_count_rejected():
    bad = registry()
    bad["completed_batches"][0]["active_annual_replays"] = True
    with pytest.raises(ValueError):
        dashboard_model(bad)
