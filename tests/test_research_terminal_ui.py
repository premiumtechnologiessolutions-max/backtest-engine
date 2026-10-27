"""Read-only premium terminal rendering and injection regression tests."""
import pytest
from scripts.research_terminal_ui import render_premium_html


def _model():
    return {
        "updated_utc": "2026-10-27T18:14:13Z",
        "research_status": "HISTORICALLY_EXPOSED_DESIGN_ONLY_NOT_OOS",
        "specifications": 2,
        "annual_replays": 4,
        "families": 1,
        "passing_24_of_24": 0,
        "fee": 0.40,
        "rows": [{
            "id": "NRF-FAC-001",
            "family": 'Breakout <img src=x onerror=alert(1)>',
            "specs": 2,
            "active_replays": 4,
            "best_positive_months": 18,
            "passing_24_of_24": 0,
            "status": "REJECTED_EXPOSED_DESIGN",
            "report": "docs/ONE.md",
        }],
    }


def test_premium_dashboard_contains_sections_and_audited_metrics():
    html = render_premium_html(_model())
    for text in (
        "NO RISK FX", "Quant Research", "Strategy Lab", "Verification",
        "319,836",
    ):
        if text == "319,836":
            assert text not in html  # no fabricated global totals from fixtures
        else:
            assert text in html
    assert "Read evidence" in html
    assert "24/24 PASS" in html
    assert 'id="experimentRows"' in html
    assert "not independently proven strategies" in html


def test_escapes_untrusted_rows_and_status_without_inline_executable_data():
    model = _model()
    model["rows"][0]["status"] = '<svg/onload=alert(1)>'
    html = render_premium_html(model)
    assert '<img src=x onerror=alert(1)>' not in html
    assert '<svg/onload=alert(1)>' not in html
    assert "&lt;img" in html
    assert "&lt;svg" in html
    assert 'href="javascript:' not in html
    assert "<script src=" not in html


@pytest.mark.parametrize("bad", [
    "javascript:alert(1)", "../../secret.csv", "docs/../../secret.csv",
    "https://attacker.example/path", "docs/<unsafe>.md", "docs\\windows.md",
])
def test_fail_closed_evidence_paths(bad):
    model = _model()
    model["rows"][0]["report"] = bad
    with pytest.raises(ValueError, match="Unsafe evidence path"):
        render_premium_html(model)


@pytest.mark.parametrize("bad", [-1, 25, True, 1.5, "24"])
def test_positive_months_must_be_bounded_integer(bad):
    model = _model()
    model["rows"][0]["best_positive_months"] = bad
    with pytest.raises(ValueError, match="Best positive months"):
        render_premium_html(model)


def test_offline_mobile_and_comparison_controls_are_present():
    html = render_premium_html(_model())
    assert 'name="viewport"' in html
    assert 'id="filter"' in html
    assert 'id="statusFilter"' in html
    assert 'id="sort"' in html
    assert 'id="clearCompare"' in html
    assert 'type="checkbox"' in html
    assert "Maximum 3 families" in html
    assert 'aria-live="polite"' in html
    assert "https://cdn." not in html


def test_zero_families_empty_state():
    model = _model()
    model["rows"] = []
    html = render_premium_html(model)
    assert "No active families in audited registry" in html
    assert '<tbody id="experimentRows"></tbody>' in html
