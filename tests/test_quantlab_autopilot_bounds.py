"""Autopilot regression: explicit budget, safe shutdown, no silent OOS claim.

Tests do not access any genuine Gold quotes; all execution is mocked.
"""
from __future__ import annotations

from pathlib import Path
import threading
import pytest

from scripts import quantlab_desktop as app


@pytest.fixture
def hub(tmp_path, monkeypatch):
    source = tmp_path / "fake-source.zip"
    source.write_bytes(b"SYNTHETIC_TEST_ONLY")
    true_sha = app.lab.file_sha
    monkeypatch.setattr(
        app.lab, "file_sha",
        lambda p: app.SOURCE_SHA if Path(p) == source else true_sha(p),
    )
    monkeypatch.setattr(app.lab, "checkout_commit", lambda: "a" * 40)
    h = app.ResearchHub(tmp_path / "workspace")
    h.configure(str(source))
    return h


def frozen(hub):
    return hub.freeze({
        "year": 2012, "strategy": "ema", "timeframe": "M15",
        "execution": "fast", "grid": {
            "fast": [8, 9], "slow": [21], "rr": [1.5, 2.0],
        },
    })["plan_id"]


def test_autopilot_never_exceeds_explicit_budget(hub, monkeypatch):
    ident = frozen(hub)
    launches = []
    def run(plan, output, *, max_jobs, recover_verified_orphans):
        launches.append(max_jobs)
        return {
            "executed_this_invocation": max_jobs,
            "reconciled_jobs": sum(launches),
            "defined_jobs": 100,
            "status": "HISTORICAL_RESEARCH_ONLY",
        }
    monkeypatch.setattr(app.lab, "run_plan", run)
    answer = hub.start_autopilot(ident, 3, 5)
    assert answer["total_budget"] == 5
    hub._thread.join(4)
    assert launches == [3, 2]
    assert hub.status()["operator_budget_completed"] == 5
    assert hub.status()["active_run"] is None


def test_stop_cooperatively_between_verified_batches(hub, monkeypatch):
    ident = frozen(hub)
    entered, released = threading.Event(), threading.Event()
    calls = []
    def run(plan, output, *, max_jobs, recover_verified_orphans):
        calls.append(max_jobs)
        entered.set()
        assert released.wait(4)
        return {
            "executed_this_invocation": 1, "reconciled_jobs": 1,
            "defined_jobs": 4, "status": "HISTORICAL_RESEARCH_ONLY",
        }
    monkeypatch.setattr(app.lab, "run_plan", run)
    hub.start_autopilot(ident, 1, 4)
    try:
        assert entered.wait(3)
        assert hub.stop_autopilot(ident)["status"] == "STOP_REQUESTED_AFTER_CURRENT_BATCH"
        with pytest.raises(ValueError, match="active"):
            hub.start(ident, 1)
    finally:
        released.set()
        hub._thread.join(4)
    assert calls == [1]
    assert hub.status()["active_run"] is None


def test_fail_closed_without_progress(hub, monkeypatch):
    ident = frozen(hub)
    calls = []
    def no_progress(*args, **kwargs):
        calls.append(1)
        return {
            "executed_this_invocation": 0,
            "reconciled_jobs": 0,
            "defined_jobs": 4,
            "status": "HISTORICAL_RESEARCH_ONLY",
        }
    monkeypatch.setattr(app.lab, "run_plan", no_progress)
    hub.start_autopilot(ident, 1, 4)
    hub._thread.join(4)
    assert calls == [1]
    assert "no progress" in hub.run_summary(ident)["last_error"]


@pytest.mark.parametrize("batch,budget", [
    (0, 5), (101, 5), (True, 5), (1, 0), (1, 5001), (1, True),
])
def test_budget_rejected_before_research(hub, batch, budget):
    ident = frozen(hub)
    with pytest.raises(ValueError):
        hub.start_autopilot(ident, batch, budget)


def test_empty_pagination_and_invalid_limit(hub):
    ident = frozen(hub)
    data = hub.run_results(ident, offset=0, limit=1)
    assert data["jobs"] == []
    with pytest.raises(ValueError):
        hub.run_results(ident, offset=-1, limit=20)
    with pytest.raises(ValueError):
        hub.run_results(ident, offset=0, limit=201)


@pytest.mark.parametrize("bad", [
    None,
    {"executed_this_invocation": True, "reconciled_jobs": 0, "defined_jobs": 4},
    {"executed_this_invocation": 2, "reconciled_jobs": 0, "defined_jobs": 4},
    {"executed_this_invocation": 0, "reconciled_jobs": True, "defined_jobs": 4},
    {"executed_this_invocation": 0, "reconciled_jobs": 5, "defined_jobs": 4},
    {"executed_this_invocation": 0, "reconciled_jobs": 0, "defined_jobs": 5001},
])
def test_autopilot_rejects_invalid_runner_progress_without_budget_credit(hub, monkeypatch, bad):
    ident = frozen(hub)
    monkeypatch.setattr(app.lab, "run_plan", lambda *a, **k: bad)
    hub.start_autopilot(ident, 1, 4)
    hub._thread.join(4)
    assert "ValueError" in hub.run_summary(ident)["last_error"]
    assert hub.status()["operator_budget_completed"] == 0
    assert hub.status()["active_run"] is None
