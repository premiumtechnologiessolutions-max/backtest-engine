"""Synthetic-only worker tests: no private XAUUSD source, no broker or network."""
from contextlib import contextmanager
import json
import os
from pathlib import Path

import pytest

from scripts import research_job_worker as worker


def fixture(tmp_path, monkeypatch):
    fingerprint = "a" * 64
    month = "2012-01"
    slot = {"month": month, "start_utc": "2012-01-01",
            "end_exclusive_utc": "2012-02-01"}
    monkeypatch.setattr(worker, "verify_plan", lambda root, fp: {
        "request_fingerprint": fp, "slots": [slot]})
    monkeypatch.setattr(worker, "preflight_job", lambda root, fp: {
        "source_commit": "b" * 40})
    plan = {
        "schema": worker.lab.SCHEMA,
        "dataset": "/private/Gold data.zip",
        "source_sha256": worker.SOURCE_SHA,
        "engine_commit": "b" * 40,
        "exposure_context": "historical_exposed",
        "jobs": [{
            "id": "synthetic-1", "strategy": "ema", "timeframe": "M15",
            "execution": "fast", "start": "2012-01-01", "end": "2012-01-31",
            "parameters": {"fast": 5, "slow": 15, "stop_atr": 1.5, "rr": 2.0}
        }],
        "grids": [],
    }
    path = tmp_path / "private-plan.json"
    path.write_text(json.dumps(plan))
    path.chmod(0o600)
    return fingerprint, month, path, plan


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-only worker")
def test_bind_is_idempotent_and_no_execution(tmp_path, monkeypatch):
    fingerprint, month, path, plan = fixture(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError("Canonical runner must not run during bind")
    monkeypatch.setattr(worker.lab, "run_plan", forbidden)
    first = worker.bind_plan(tmp_path, fingerprint, month, path)
    assert first["status"] == "BOUND_NOT_EXECUTED"
    assert first["defined_jobs"] == 1
    assert worker.bind_plan(tmp_path, fingerprint, month, path) == first
    bound = worker._bound_path(tmp_path, fingerprint, month)
    assert bound.stat().st_mode & 0o077 == 0
    assert worker._bound(tmp_path, fingerprint, month)[1] == 1


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-only worker")
def test_run_defaults_to_safe_plan_only(tmp_path, monkeypatch):
    fingerprint, month, path, plan = fixture(tmp_path, monkeypatch)
    worker.bind_plan(tmp_path, fingerprint, month, path)
    monkeypatch.setattr(worker.lab, "run_plan",
                        lambda *args, **kwargs: pytest.fail("executed without --execute"))
    result = worker.run_month(tmp_path, fingerprint, month)
    assert result["status"] == "VERIFIED_PLAN_ONLY_NOT_EXECUTED"
    assert result["monthly_pnl_observations"] == 0
    assert not (tmp_path / "reports" / "research_job_runs").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-only worker")
def test_explicit_run_uses_lease_and_bounded_canonical_runner(tmp_path, monkeypatch):
    fingerprint, month, path, plan = fixture(tmp_path, monkeypatch)
    worker.bind_plan(tmp_path, fingerprint, month, path)
    calls = []
    @contextmanager
    def fake_lease(root, fp, mo):
        calls.append(("lock", fp, mo))
        yield {}
    def fake_runner(frozen, out, **kwargs):
        assert calls[0][0] == "lock"
        assert frozen == plan
        assert kwargs == {"max_jobs": 2}
        assert out.is_dir()
        assert out.stat().st_mode & 0o077 == 0
        calls.append(("run", out))
        return {"status": "HISTORICAL_RESEARCH_ONLY",
                "executed_this_invocation": 0, "reconciled_jobs": 1}
    monkeypatch.setattr(worker, "reserve_closed_month", fake_lease)
    monkeypatch.setattr(worker.lab, "run_plan", fake_runner)
    result = worker.run_month(tmp_path, fingerprint, month, execute=True, max_jobs=2)
    assert result["historical_exposed_not_oos"] is True
    assert result["executed_this_invocation"] == 0
    assert [c[0] for c in calls] == ["lock", "run"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-only worker")
def test_rejects_tampered_bound_snapshot(tmp_path, monkeypatch):
    fingerprint, month, path, plan = fixture(tmp_path, monkeypatch)
    worker.bind_plan(tmp_path, fingerprint, month, path)
    bound = worker._bound_path(tmp_path, fingerprint, month)
    bound.write_text(bound.read_text().replace("synthetic-1", "synthetic-2"))
    with pytest.raises(ValueError, match="noncanonical|fingerprint"):
        worker.run_month(tmp_path, fingerprint, month)


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-only worker")
def test_changed_bound_plan_cannot_replace(tmp_path, monkeypatch):
    fingerprint, month, path, plan = fixture(tmp_path, monkeypatch)
    worker.bind_plan(tmp_path, fingerprint, month, path)
    plan["jobs"][0]["parameters"]["fast"] = 6
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="never overwrite"):
        worker.bind_plan(tmp_path, fingerprint, month, path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-only worker")
@pytest.mark.parametrize("change", [
    {"source_sha256": "0" * 64},
    {"engine_commit": "c" * 40},
    {"exposure_context": "prospective"},
])
def test_rejects_wrong_source_commit_or_exposure(tmp_path, monkeypatch, change):
    fingerprint, month, path, plan = fixture(tmp_path, monkeypatch)
    plan.update(change)
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError):
        worker.bind_plan(tmp_path, fingerprint, month, path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-only worker")
def test_rejects_cross_month_execution_window(tmp_path, monkeypatch):
    fingerprint, month, path, plan = fixture(tmp_path, monkeypatch)
    plan["jobs"][0]["end"] = "2012-02-01"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="exactly the frozen UTC month"):
        worker.bind_plan(tmp_path, fingerprint, month, path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-only worker")
def test_rejects_duplicate_json_and_loose_permissions(tmp_path, monkeypatch):
    fingerprint, month, path, plan = fixture(tmp_path, monkeypatch)
    path.write_text('{"schema":1,"schema":2}')
    with pytest.raises(ValueError, match="Duplicate"):
        worker.bind_plan(tmp_path, fingerprint, month, path)
    path.write_text(json.dumps(plan))
    path.chmod(0o644)
    with pytest.raises(ValueError, match="owner-only"):
        worker.bind_plan(tmp_path, fingerprint, month, path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX owner-only worker")
def test_rejects_symlinked_private_plan(tmp_path, monkeypatch):
    fingerprint, month, path, plan = fixture(tmp_path, monkeypatch)
    alias = tmp_path / "alias.json"
    alias.symlink_to(path)
    with pytest.raises(ValueError, match="Symlinked"):
        worker.bind_plan(tmp_path, fingerprint, month, alias)


@pytest.mark.parametrize("bad", [0, 21, True, 1.5])
def test_rejects_unbounded_execution_budget(tmp_path, bad):
    with pytest.raises(ValueError, match="max-jobs"):
        worker.run_month(tmp_path, "a" * 64, "2012-01", max_jobs=bad)
