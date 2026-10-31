"""Synthetic-only tests for read-only frozen research job preflight."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from scripts.research_job_queue import enqueue, frozen_request
from scripts import research_job_preflight as gate


def queued(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "research").mkdir()
    (tmp_path / "docs" / "FAC025_FROZEN.md").write_text("Frozen hypothesis\n")
    (tmp_path / "research" / "strategy_factory_registry.json").write_text(
        json.dumps({"completed_batches": []}))
    job = frozen_request(tmp_path, "NRF-FAC-025", "docs/FAC025_FROZEN.md",
                         "a" * 40, "2026-11-01", "2027-10-31")
    enqueue(tmp_path, job)
    return job


def test_preflight_validates_actual_checkout_but_never_executes(tmp_path, monkeypatch):
    job = queued(tmp_path)
    monkeypatch.setattr(gate, "_git_head", lambda root: "a" * 40)
    result = gate.preflight_job(tmp_path, job["fingerprint"])
    assert result["status"] == "MATCHED_METADATA_ONLY_NOT_EXECUTED"
    assert result["backtests_executed"] == 0
    assert result["monthly_pnl_observations"] == 0
    assert result["source_commit"] == "a" * 40
    assert result["frozen_spec_sha256"] == job["frozen_spec_sha256"]


def test_preflight_rejects_modified_spec(tmp_path, monkeypatch):
    job = queued(tmp_path)
    (tmp_path / "docs" / "FAC025_FROZEN.md").write_text("Edited after queue\n")
    monkeypatch.setattr(gate, "_git_head", lambda root: "a" * 40)
    with pytest.raises(ValueError, match="specification changed"):
        gate.preflight_job(tmp_path, job["fingerprint"])


def test_preflight_rejects_modified_registry(tmp_path, monkeypatch):
    job = queued(tmp_path)
    (tmp_path / "research" / "strategy_factory_registry.json").write_text(
        json.dumps({"completed_batches": ["modified"]}))
    monkeypatch.setattr(gate, "_git_head", lambda root: "a" * 40)
    with pytest.raises(ValueError, match="registry changed"):
        gate.preflight_job(tmp_path, job["fingerprint"])


def test_preflight_rejects_wrong_checkout(tmp_path, monkeypatch):
    job = queued(tmp_path)
    monkeypatch.setattr(gate, "_git_head", lambda root: "b" * 40)
    with pytest.raises(ValueError, match="checkout HEAD differs"):
        gate.preflight_job(tmp_path, job["fingerprint"])


@pytest.mark.parametrize("fingerprint", [None, True, "a" * 63, "Z" * 64, "../../etc"])
def test_preflight_rejects_invalid_fingerprint(tmp_path, fingerprint):
    with pytest.raises(ValueError, match="Invalid queue fingerprint"):
        gate.preflight_job(tmp_path, fingerprint)


def test_preflight_rejects_unknown_valid_fingerprint(tmp_path):
    queued(tmp_path)
    with pytest.raises(ValueError, match="not found"):
        gate.preflight_job(tmp_path, "b" * 64)


def test_preflight_rejects_tampered_queue(tmp_path):
    job = queued(tmp_path)
    path = tmp_path / "reports" / "research_jobs" / (job["fingerprint"] + ".json")
    path.write_text("not json")
    with pytest.raises(ValueError):
        gate.preflight_job(tmp_path, job["fingerprint"])


def test_git_head_uses_no_shell_and_rejects_bad_output(tmp_path, monkeypatch):
    def fake_run(argv, **kwargs):
        assert argv == ["git", "rev-parse", "--verify", "HEAD"]
        assert kwargs["cwd"] == tmp_path
        assert kwargs["timeout"] == 5 and kwargs["check"] is True
        assert "shell" not in kwargs
        return SimpleNamespace(stdout="not-a-sha\n")
    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="Invalid local Git"):
        gate._git_head(tmp_path)


def test_git_head_fails_closed_if_git_unavailable(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=5)
    monkeypatch.setattr(gate.subprocess, "run", fail)
    with pytest.raises(ValueError, match="Cannot verify"):
        gate._git_head(tmp_path)


def test_git_head_rejects_dirty_tracked_checkout(tmp_path, monkeypatch):
    calls = []
    def fake_run(argv, **kwargs):
        calls.append(argv)
        assert kwargs["cwd"] == tmp_path
        assert kwargs["check"] is True and kwargs["timeout"] == 5
        if argv == ["git", "rev-parse", "--verify", "HEAD"]:
            return SimpleNamespace(stdout="a" * 40 + "\n")
        assert argv == ["git", "status", "--porcelain", "--untracked-files=no"]
        return SimpleNamespace(stdout=" M src/norisk_quant/execution.py\n")
    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="Tracked checkout differs"):
        gate._git_head(tmp_path)
    assert len(calls) == 2


def test_git_head_accepts_clean_tracked_checkout(tmp_path, monkeypatch):
    def fake_run(argv, **kwargs):
        if argv == ["git", "rev-parse", "--verify", "HEAD"]:
            return SimpleNamespace(stdout="a" * 40 + "\n")
        if argv == ["git", "status", "--porcelain", "--untracked-files=no"]:
            return SimpleNamespace(stdout="")
        assert argv == ["git", "ls-files", "--others", "--exclude-standard", "--", "src", "scripts"]
        return SimpleNamespace(stdout="")
    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    assert gate._git_head(tmp_path) == "a" * 40


def test_git_head_rejects_failed_cleanliness_probe(tmp_path, monkeypatch):
    def fake_run(argv, **kwargs):
        if argv == ["git", "rev-parse", "--verify", "HEAD"]:
            return SimpleNamespace(stdout="a" * 40 + "\n")
        raise subprocess.TimeoutExpired(cmd="git status", timeout=5)
    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="Cannot verify tracked checkout cleanliness"):
        gate._git_head(tmp_path)



def test_git_head_rejects_untracked_importable_source(tmp_path, monkeypatch):
    calls = []
    def fake_run(argv, **kwargs):
        calls.append(argv)
        assert kwargs["cwd"] == tmp_path and kwargs["check"] is True
        if argv == ["git", "rev-parse", "--verify", "HEAD"]:
            return SimpleNamespace(stdout="a" * 40 + "\n")
        if argv == ["git", "status", "--porcelain", "--untracked-files=no"]:
            return SimpleNamespace(stdout="")
        assert argv == ["git", "ls-files", "--others", "--exclude-standard", "--", "src", "scripts"]
        return SimpleNamespace(stdout="src/norisk_quant/rogue.py\n")
    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="Untracked source files"):
        gate._git_head(tmp_path)
    assert len(calls) == 3


def test_git_head_fails_closed_when_untracked_probe_times_out(tmp_path, monkeypatch):
    def fake_run(argv, **kwargs):
        if argv == ["git", "rev-parse", "--verify", "HEAD"]:
            return SimpleNamespace(stdout="a" * 40 + "\n")
        if argv == ["git", "status", "--porcelain", "--untracked-files=no"]:
            return SimpleNamespace(stdout="")
        raise subprocess.TimeoutExpired(cmd="git ls-files", timeout=5)
    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="Cannot verify untracked source cleanliness"):
        gate._git_head(tmp_path)


def test_git_head_real_repository_detects_untracked_python(tmp_path):
    """Integration regression: Git HEAD alone must not bless a shadow module."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    source = tmp_path / "src" / "norisk_quant"
    source.mkdir(parents=True)
    (source / "known.py").write_text("VALUE = 1\n")
    subprocess.run(["git", "add", "src/norisk_quant/known.py"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Quant Test", "-c", "user.email=quant@example.invalid",
         "commit", "-qm", "fixture"], cwd=tmp_path, check=True,
    )
    assert gate._git_head(tmp_path) == subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    (source / "shadow.py").write_text("VALUE = 2\n")
    with pytest.raises(ValueError, match="Untracked source files"):
        gate._git_head(tmp_path)
