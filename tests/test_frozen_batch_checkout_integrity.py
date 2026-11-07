"""Regression tests: frozen batch revision must bind importable source, not only HEAD."""
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from scripts import research_batch_orchestrator as lab

HEAD = "a" * 40


def test_frozen_batch_rejects_untracked_importable_source(monkeypatch):
    def fake_run(argv, **kwargs):
        if "rev-parse" in argv:
            return SimpleNamespace(stdout=HEAD)
        if "status" in argv:
            return SimpleNamespace(stdout="")
        if "ls-files" in argv:
            assert argv[-2:] == ["src", "scripts"]
            return SimpleNamespace(stdout="src/norisk_quant/rogue.py\n")
        raise AssertionError(f"Unexpected git command: {argv}")

    monkeypatch.setattr(lab.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="Untracked research source"):
        lab.checkout_commit()


def test_frozen_batch_accepts_clean_source(monkeypatch):
    def fake_run(argv, **kwargs):
        if "rev-parse" in argv:
            return SimpleNamespace(stdout=HEAD)
        if "status" in argv or "ls-files" in argv:
            return SimpleNamespace(stdout="")
        raise AssertionError(f"Unexpected git command: {argv}")

    monkeypatch.setattr(lab.subprocess, "run", fake_run)
    assert lab.checkout_commit() == HEAD


def test_frozen_batch_rejects_failed_untracked_probe(monkeypatch):
    def fake_run(argv, **kwargs):
        if "rev-parse" in argv:
            return SimpleNamespace(stdout=HEAD)
        if "status" in argv:
            return SimpleNamespace(stdout="")
        if "ls-files" in argv:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=10)
        raise AssertionError(f"Unexpected git command: {argv}")

    monkeypatch.setattr(lab.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="Cannot verify untracked research source"):
        lab.checkout_commit()


def test_frozen_batch_rejects_tracked_modification_before_untracked_probe(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if "rev-parse" in argv:
            return SimpleNamespace(stdout=HEAD)
        if "status" in argv:
            return SimpleNamespace(stdout=" M src/norisk_quant/core.py\n")
        raise AssertionError("Must stop before further probes")

    monkeypatch.setattr(lab.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="Uncommitted changes"):
        lab.checkout_commit()
    assert len(calls) == 2


def test_frozen_batch_real_git_checkout_detects_untracked_source(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    tracked = scripts / "research_batch_orchestrator.py"
    tracked.write_text("# frozen\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "baseline"], check=True)
    monkeypatch.setattr(lab, "__file__", str(tracked))
    expected = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert lab.checkout_commit() == expected
    rogue = tmp_path / "src" / "norisk_quant" / "rogue.py"
    rogue.parent.mkdir(parents=True)
    rogue.write_text("DANGEROUS = True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Untracked research source"):
        lab.checkout_commit()
