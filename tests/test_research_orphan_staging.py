"""Synthetic interrupted staging is retained but never certified as a backtest."""
import os

import pytest

from scripts.research_batch_orchestrator import exclusive_batch_lock
from scripts.research_orphan_staging import (
    QUARANTINE, quarantine_abandoned_staging_locked,
)


def _root(tmp_path):
    root = tmp_path / "private-research"
    root.mkdir()
    (root / "generation_0001").mkdir()
    return root


def _quarantine(root):
    with exclusive_batch_lock(root):
        return quarantine_abandoned_staging_locked(root)


def test_interrupted_replay_moved_without_deleting_forensic_bytes(tmp_path):
    root = _root(tmp_path)
    stage = root / "generation_0001" / ".nrfx_arithmetic_training_abc123"
    stage.mkdir()
    (stage / "replay-partial.csv").write_bytes(b"private partial evidence")
    verified = root / "generation_0001" / "replay_2012_from_001_count_002"
    verified.mkdir()
    (verified / "training_replay_index.json").write_text("verified not rewritten")
    names = _quarantine(root)
    assert names == ["generation_0001__.nrfx_arithmetic_training_abc123"]
    assert not stage.exists()
    dest = root / QUARANTINE / names[0] / "replay-partial.csv"
    assert dest.read_bytes() == b"private partial evidence"
    assert (verified / "training_replay_index.json").read_text() == "verified not rewritten"
    assert _quarantine(root) == []
    if os.name == "posix":
        assert (root / QUARANTINE).stat().st_mode & 0o077 == 0


def test_malicious_staging_symlink_blocks_any_quarantine(tmp_path):
    root = _root(tmp_path)
    good = root / "generation_0001" / ".nrfx_arithmetic_training_valid"
    good.mkdir()
    bad = root / "generation_0001" / ".nrfx_arithmetic_training_bad"
    bad.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="Unsafe interrupted"):
        _quarantine(root)
    assert good.exists()
    assert not (root / QUARANTINE).exists()


def test_embedded_symlink_blocks_any_quarantine(tmp_path):
    root = _root(tmp_path)
    stage = root / "generation_0001" / ".nrfx_arithmetic_training_partial"
    stage.mkdir()
    (stage / "link").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink/nonregular"):
        _quarantine(root)
    assert stage.exists()


def test_max_orphan_budget_fails_before_modifying_anything(tmp_path):
    root = _root(tmp_path)
    stages = []
    for i in range(3):
        stage = root / "generation_0001" / f".nrfx_arithmetic_training_{i}"
        stage.mkdir()
        stages.append(stage)
    with exclusive_batch_lock(root):
        with pytest.raises(ValueError, match="retention budget"):
            quarantine_abandoned_staging_locked(root, max_orphans=2)
    assert all(s.exists() for s in stages)
    assert not (root / QUARANTINE).exists()


def test_rejects_preexisting_public_quarantine_or_collision(tmp_path):
    root = _root(tmp_path)
    stage = root / "generation_0001" / ".nrfx_arithmetic_training_a"
    stage.mkdir()
    dest = root / QUARANTINE
    dest.mkdir()
    if os.name == "posix":
        dest.chmod(0o755)
        with pytest.raises(ValueError, match="owner-only"):
            _quarantine(root)
        assert stage.exists()
        dest.chmod(0o700)
    (dest / "generation_0001__.nrfx_arithmetic_training_a").mkdir()
    with pytest.raises(FileExistsError, match="already quarantined"):
        _quarantine(root)
    assert stage.exists()


@pytest.mark.parametrize("budget", [0, True, -1, 1025])
def test_reject_bad_quarantine_budget(tmp_path, budget):
    root = _root(tmp_path)
    with exclusive_batch_lock(root):
        with pytest.raises(ValueError, match="budget"):
            quarantine_abandoned_staging_locked(root, max_orphans=budget)
