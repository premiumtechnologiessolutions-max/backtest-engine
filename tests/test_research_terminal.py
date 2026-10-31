"""Fail-closed tests for the research-only static terminal."""
import json
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
    assert "NO RISK FX" in html and "Strategy Lab" in html


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


def _local_queue_fixture(tmp_path):
    from scripts.research_job_queue import enqueue, frozen_request
    data = registry()
    (tmp_path / "docs").mkdir()
    (tmp_path / "research").mkdir()
    (tmp_path / "docs" / "FAC024_FROZEN.md").write_text("Frozen source\\n")
    registry_file = tmp_path / "research" / "strategy_factory_registry.json"
    registry_file.write_text(json.dumps(data))
    job = frozen_request(tmp_path, "NRF-FAC-024", "docs/FAC024_FROZEN.md",
                         "a" * 40, "2026-11-01", "2027-10-31")
    enqueue(tmp_path, job)
    return registry_file, job


def test_local_queue_is_opt_in_and_never_claims_execution(tmp_path, monkeypatch):
    from scripts import research_terminal as terminal
    registry_file, job = _local_queue_fixture(tmp_path)
    monkeypatch.setattr(terminal, "ROOT", tmp_path)
    output = tmp_path / "terminal.html"
    assert terminal.main(["--registry", str(registry_file), "--out", str(output)]) == 0
    default_html = output.read_text()
    assert job["fingerprint"] not in default_html
    assert "Local queue not loaded" in default_html
    assert terminal.main(["--registry", str(registry_file), "--out", str(output),
                          "--include-local-jobs"]) == 0
    html = output.read_text()
    assert job["fingerprint"] in html
    assert "QUEUED · NOT EXECUTED" in html
    assert "Preflight: N/A" in html
    assert "floating drawdown: N/A" in html
    assert "Research Jobs" in html
    assert "<script src=" not in html


def test_tampered_queue_prevents_dashboard_export(tmp_path, monkeypatch):
    from scripts import research_terminal as terminal
    registry_file, job = _local_queue_fixture(tmp_path)
    monkeypatch.setattr(terminal, "ROOT", tmp_path)
    queue_file = tmp_path / "reports" / "research_jobs" / (job["fingerprint"] + ".json")
    queue_file.write_text('{"status":"COMPLETED"}')
    output = tmp_path / "terminal.html"
    with pytest.raises(ValueError):
        terminal.main(["--registry", str(registry_file), "--out", str(output),
                       "--include-local-jobs"])
    assert not output.exists()


def test_render_rejects_unverified_job_status():
    model = dashboard_model(registry())
    model["jobs"] = [{
        "fingerprint": "a" * 64, "source_commit": "b" * 40,
        "family": "NRF-FAC-024", "evaluation_start": "2026-11-01",
        "evaluation_end": "2027-10-31", "status": "COMPLETED",
    }]
    with pytest.raises(ValueError, match="Unverified local research job"):
        render_html(model)


def test_opt_in_empty_queue_is_explicit(tmp_path, monkeypatch):
    from scripts import research_terminal as terminal
    (tmp_path / "research").mkdir()
    path = tmp_path / "research" / "strategy_factory_registry.json"
    path.write_text(json.dumps(registry()))
    monkeypatch.setattr(terminal, "ROOT", tmp_path)
    output = tmp_path / "terminal.html"
    assert terminal.main(["--registry", str(path), "--out", str(output),
                          "--include-local-jobs"]) == 0
    assert "No queued local requests" in output.read_text()


def test_month_plan_opt_in_renders_verified_snapshot_only(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from scripts import research_terminal as terminal
    from scripts import research_job_plan_snapshot as snap
    from scripts.research_job_month_plan import plan_month_slots
    registry_file, job = _local_queue_fixture(tmp_path)
    monkeypatch.setattr(terminal, "ROOT", tmp_path)
    slots = plan_month_slots(job, datetime(2026, 10, 28, tzinfo=timezone.utc))
    monkeypatch.setattr(snap, "plan_job", lambda root, fingerprint: {
        "request_fingerprint": fingerprint, "planning_only": True, "slots": slots,
    })
    snap.persist_plan(tmp_path, job["fingerprint"])
    output = tmp_path / "terminal.html"
    assert terminal.main(["--registry", str(registry_file), "--out", str(output),
                          "--include-local-jobs"]) == 0
    assert "Monthly plan snapshots not loaded" in output.read_text()
    assert job["fingerprint"][:16] in output.read_text()
    assert terminal.main(["--registry", str(registry_file), "--out", str(output),
                          "--include-local-jobs", "--include-local-month-plans"]) == 0
    html = output.read_text()
    assert "Verified immutable monthly plans" in html
    assert "2026-11" in html and "2027-10" in html
    assert "12 planned UTC months" in html
    assert "PLANNED · NOT EXECUTED" in html
    assert "Floating M1 DD" in html and "N/A" in html
    assert "0 executed" in html


def test_month_plan_flag_requires_explicit_local_queue_optin(tmp_path, monkeypatch):
    from scripts import research_terminal as terminal
    registry_file, _ = _local_queue_fixture(tmp_path)
    monkeypatch.setattr(terminal, "ROOT", tmp_path)
    with pytest.raises(SystemExit) as exc:
        terminal.main(["--registry", str(registry_file),
                       "--out", str(tmp_path / "terminal.html"),
                       "--include-local-month-plans"])
    assert exc.value.code == 2
    assert not (tmp_path / "terminal.html").exists()


def test_missing_month_plan_fails_closed_without_export(tmp_path, monkeypatch):
    from scripts import research_terminal as terminal
    registry_file, _ = _local_queue_fixture(tmp_path)
    monkeypatch.setattr(terminal, "ROOT", tmp_path)
    output = tmp_path / "terminal.html"
    with pytest.raises((ValueError, FileNotFoundError)):
        terminal.main(["--registry", str(registry_file), "--out", str(output),
                       "--include-local-jobs", "--include-local-month-plans"])
    assert not output.exists()


def test_render_rejects_forged_completed_month_plan():
    model = dashboard_model(registry())
    model["monthly_plans"] = [{
        "schema_version": 1, "request_fingerprint": "a" * 64,
        "status": "COMPLETED", "source_verified_months": 12,
        "backtests_executed": 100, "slots": [], "snapshot_sha256": "b" * 64,
    }]
    with pytest.raises(ValueError, match="provenance|state"):
        render_html(model)


def test_cli_explicit_sha_targeted_report_link(tmp_path):
    from scripts import research_terminal as terminal
    registry_file = tmp_path / "registry.json"
    registry_file.write_text(json.dumps(registry()), encoding="utf-8")
    out = tmp_path / "terminal.html"
    sha = "b" * 40
    assert terminal.main(["--registry", str(registry_file), "--out", str(out),
                          "--evidence-commit", sha]) == 0
    html = out.read_text(encoding="utf-8")
    assert f"/blob/{sha}/docs/ONE.md" in html
    assert "SHA-targeted; target not verified" in html


def test_cli_invalid_sha_target_rejected_before_output(tmp_path):
    from scripts import research_terminal as terminal
    registry_file = tmp_path / "registry.json"
    registry_file.write_text(json.dumps(registry()), encoding="utf-8")
    out = tmp_path / "terminal.html"
    with pytest.raises(SystemExit) as exc:
        terminal.main(["--registry", str(registry_file), "--out", str(out),
                       "--evidence-commit", "main"])
    assert exc.value.code == 2
    assert not out.exists()
