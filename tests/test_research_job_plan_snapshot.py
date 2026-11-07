"""Synthetic tests only: no private quotes, trading or real execution."""
from datetime import datetime, timezone
import json
import os
import pytest

from scripts import research_job_plan_snapshot as snap
from scripts.research_job_month_plan import plan_month_slots

FINGERPRINT = "a" * 64


def _mock_plan(monkeypatch, *, start="2026-11-01", end="2027-10-31"):
    job = {"fingerprint": FINGERPRINT, "evaluation_start": start, "evaluation_end": end}
    slots = plan_month_slots(job, datetime(2026, 10, 28, tzinfo=timezone.utc))
    def planner(root, fingerprint):
        assert fingerprint == FINGERPRINT
        return {"request_fingerprint": fingerprint, "planning_only": True, "slots": slots}
    monkeypatch.setattr(snap, "plan_job", planner)
    return slots


def test_snapshot_persists_12_future_slots_without_claiming_results(tmp_path, monkeypatch):
    _mock_plan(monkeypatch)
    saved = snap.persist_plan(tmp_path, FINGERPRINT)
    assert len(saved["slots"]) == 12
    assert saved["status"] == "PLANNED_ONLY_NOT_EXECUTED"
    assert saved["backtests_executed"] == saved["source_verified_months"] == 0
    assert "monthly_net_pnl" not in json.dumps(saved)
    assert snap.verify_plan(tmp_path, FINGERPRINT) == saved
    assert snap.persist_plan(tmp_path, FINGERPRINT) == saved


def test_drift_of_frozen_slot_plan_is_rejected(tmp_path, monkeypatch):
    _mock_plan(monkeypatch)
    snap.persist_plan(tmp_path, FINGERPRINT)
    _mock_plan(monkeypatch, end="2026-11-30")
    with pytest.raises(ValueError, match="stale|differs"):
        snap.verify_plan(tmp_path, FINGERPRINT)
    with pytest.raises(ValueError, match="differs"):
        snap.persist_plan(tmp_path, FINGERPRINT)


def test_tampered_snapshot_is_rejected_even_if_json_is_valid(tmp_path, monkeypatch):
    _mock_plan(monkeypatch)
    snap.persist_plan(tmp_path, FINGERPRINT)
    path = tmp_path / "reports" / "research_jobs" / "monthly_plans" / (FINGERPRINT + ".json")
    data = json.loads(path.read_text())
    data["status"] = "COMPLETED"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="changed"):
        snap.verify_plan(tmp_path, FINGERPRINT)


def test_preflight_failure_makes_no_directory(tmp_path, monkeypatch):
    def deny(*args):
        raise ValueError("frozen metadata changed")
    monkeypatch.setattr(snap, "plan_job", deny)
    with pytest.raises(ValueError, match="frozen"):
        snap.persist_plan(tmp_path, FINGERPRINT)
    assert not (tmp_path / "reports").exists()


@pytest.mark.parametrize("fingerprint", ["../evil", "A" * 64, "a" * 63, ""])
def test_bad_fingerprint_rejected_before_io(tmp_path, monkeypatch, fingerprint):
    _mock_plan(monkeypatch)
    with pytest.raises(ValueError, match="fingerprint"):
        snap.persist_plan(tmp_path, fingerprint)
    assert not (tmp_path / "reports").exists()


def test_symlinked_snapshot_rejected(tmp_path, monkeypatch):
    _mock_plan(monkeypatch)
    snap.persist_plan(tmp_path, FINGERPRINT)
    path = tmp_path / "reports" / "research_jobs" / "monthly_plans" / (FINGERPRINT + ".json")
    backup = path.with_suffix(".bak")
    path.rename(backup)
    try:
        path.symlink_to(backup)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="Symlinked"):
        snap.verify_plan(tmp_path, FINGERPRINT)


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
def test_world_readable_snapshot_rejected(tmp_path, monkeypatch):
    _mock_plan(monkeypatch)
    snap.persist_plan(tmp_path, FINGERPRINT)
    path = tmp_path / "reports" / "research_jobs" / "monthly_plans" / (FINGERPRINT + ".json")
    path.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        snap.verify_plan(tmp_path, FINGERPRINT)


def test_snapshot_supports_120_months_with_bounded_file(tmp_path, monkeypatch):
    _mock_plan(monkeypatch, start="2026-11-01", end="2036-10-31")
    saved = snap.persist_plan(tmp_path, FINGERPRINT)
    assert len(saved["slots"]) == 120
    assert snap.verify_plan(tmp_path, FINGERPRINT) == saved
