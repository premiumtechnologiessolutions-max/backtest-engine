"""Synthetic-only unattended host-service contracts; not real Gold evidence."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import research_unattended_service as svc


@pytest.fixture
def setup(tmp_path, monkeypatch):
    source = tmp_path / "Gold data.zip"
    source.write_bytes(b"SYNTHETIC ONLY NOT GOLD")
    out = tmp_path / "private_research"
    config = {
        "schema": svc.CONFIG_SCHEMA, "gold_zip": str(source), "out": str(out),
        "years": [2012, 2013], "seed": 42, "target_generations": 4,
        "step_generations": 2, "proposal_count": 2, "shard_size": 1,
        "min_free_gb": 0, "max_batch_wall_seconds": 60,
        "max_total_wall_seconds": 60, "max_resume_attempts": 2,
        "poll_seconds": 5, "retry_seconds": 60, "max_pause_retries": 2,
    }
    path = tmp_path / "private_config.json"
    path.write_text(json.dumps(config))
    monkeypatch.setattr(svc, "_digest", lambda _: svc.SOURCE_SHA)
    return path, out, config


def test_config_is_strict_and_prevents_implicit_shell(setup):
    path, _, original = setup
    config = svc.load_config(path)
    assert config.years == (2012, 2013)
    command = svc._worker_argv(config)
    assert command[:3] == [svc.sys.executable, "-m", "scripts.research_autonomous_director"]
    assert "--gold-zip" in command and "--target-generations" in command
    assert str(config.gold_zip) in command
    assert "matched_guided_v1" not in command  # pinned by the child
    with pytest.raises(ValueError):
        path.write_text(json.dumps({**original, "danger": "shell"}))
        svc.load_config(path)


def test_duplicate_key_and_float_overflow_rejected(setup):
    path, _, raw = setup
    path.write_text(json.dumps(raw)[:-1] + ',"seed":43}')
    with pytest.raises(ValueError, match="Duplicate"):
        svc.load_config(path)
    path.write_text(json.dumps(raw).replace('"poll_seconds": 5', '"poll_seconds": 1e999'))
    with pytest.raises(ValueError, match="Nonfinite"):
        svc.load_config(path)


@pytest.mark.parametrize("field, value", [
    ("seed", True), ("years", [2013, 2012]),
    ("target_generations", 201), ("poll_seconds", 0),
    ("gold_zip", "relative.zip"), ("max_pause_retries", -1),
])
def test_unsafe_config_rejected(setup, field, value):
    path, _, raw = setup
    raw[field] = value
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        svc.load_config(path)


@pytest.mark.parametrize("code, status, generations, expected", [
    (0, "COMPLETE_HISTORICAL_TRAINING_ONLY_NOT_OOS", 4, "TRAINING_CAP_REACHED_NOT_OOS"),
    (2, "PAUSED_DISK_BUDGET", 2, "PAUSED_DISK_BUDGET"),
    (2, "PAUSED_TOTAL_TIME_BUDGET", 1, "PAUSED_TOTAL_TIME_BUDGET"),
])
def test_child_status_is_verified_not_inferred(setup, code, status, generations, expected):
    _, root, _ = setup
    root.mkdir()
    (root / "autonomous_research_status.json").write_text(json.dumps({
        "schema": svc.DIR_SCHEMA, "status": status,
        "verified_generations": generations,
        "training_only": True, "independent_oos_proven": False,
        "live_trading_authorized": False,
    }))
    result = svc._director_result(root, None, code, 4)
    assert result == (expected, generations)


def test_false_success_and_stale_evidence_refused(setup):
    _, root, _ = setup
    root.mkdir()
    file = root / "autonomous_research_status.json"
    file.write_text(json.dumps({
        "schema": svc.DIR_SCHEMA,
        "status": "COMPLETE_HISTORICAL_TRAINING_ONLY_NOT_OOS",
        "verified_generations": 2, "training_only": True,
        "independent_oos_proven": False, "live_trading_authorized": False,
    }))
    with pytest.raises(ValueError, match="False worker completion"):
        svc._director_result(root, None, 0, 4)
    with pytest.raises(ValueError, match="stale"):
        svc._director_result(root, file.stat().st_mtime_ns, 0, 4)


def test_forged_oos_flag_rejected(setup):
    _, root, _ = setup
    root.mkdir()
    (root / "autonomous_research_status.json").write_text(json.dumps({
        "schema": svc.DIR_SCHEMA, "status": "PAUSED_DISK_BUDGET",
        "verified_generations": 0,
        "training_only": True, "independent_oos_proven": True,
        "live_trading_authorized": False,
    }))
    with pytest.raises(ValueError, match="Invalid autonomous"):
        svc._director_result(root, None, 2, 4)


class FakeChild:
    def __init__(self, root: Path, status: str, generations: int, code: int):
        self.pid = 87654
        self.returncode = code
        (root / "autonomous_research_status.json").write_text(json.dumps({
            "schema": svc.DIR_SCHEMA, "status": status,
            "verified_generations": generations,
            "training_only": True, "independent_oos_proven": False,
            "live_trading_authorized": False,
        }))

    def poll(self):
        return self.returncode


def test_complete_without_chatgpt_and_persists_health(setup):
    path, root, _ = setup
    config = svc.load_config(path)
    args_seen = []
    def launch(args, **kwargs):
        args_seen.append(args)
        return FakeChild(root, "COMPLETE_HISTORICAL_TRAINING_ONLY_NOT_OOS", 4, 0)
    status = svc.serve(config, launcher=launch, sleeper=lambda _: None)
    assert status["status"] == "TRAINING_CAP_REACHED_NOT_OOS"
    assert len(args_seen) == 1
    assert json.loads((root / "unattended_research_health.json").read_text()) == status
    assert status["live_trading_authorized"] is False
    assert "Gold data.zip" not in json.dumps(status)


def test_resource_pauses_auto_retry_then_complete(setup):
    path, root, _ = setup
    config = svc.load_config(path)
    calls = []
    def launch(args, **kwargs):
        calls.append(1)
        return (FakeChild(root, "PAUSED_TOTAL_TIME_BUDGET", 2, 2)
                if len(calls) == 1 else
                FakeChild(root, "COMPLETE_HISTORICAL_TRAINING_ONLY_NOT_OOS", 4, 0))
    sleeps = []
    report = svc.serve(config, launcher=launch, sleeper=sleeps.append)
    assert report["status"] == "TRAINING_CAP_REACHED_NOT_OOS"
    assert len(calls) == 2 and sleeps == [60]


def test_failure_stops_without_infinite_retries(setup):
    path, root, _ = setup
    config = svc.load_config(path)
    calls = []
    def launch(args, **kwargs):
        calls.append(1)
        return FakeChild(root, "FAILED_REQUIRES_EVIDENCE_REVIEW", 1, 2)
    with pytest.raises(ValueError, match="halted"):
        svc.serve(config, launcher=launch, sleeper=lambda _: None)
    assert len(calls) == 1
    status = json.loads((root / "unattended_research_health.json").read_text())
    assert status["status"] == "FAULT_REQUIRES_EVIDENCE_REVIEW"


def test_pause_retry_limit_persists_safe_state(setup):
    path, root, _ = setup
    config = replace(svc.load_config(path), max_pause_retries=1)
    calls = []
    def launch(args, **kwargs):
        calls.append(1)
        return FakeChild(root, "PAUSED_DISK_BUDGET", 0, 2)
    status = svc.serve(config, launcher=launch, sleeper=lambda _: None)
    assert len(calls) == 2
    assert status["status"] == "PAUSED_UNATTENDED_RETRY_BUDGET"


def test_invalid_source_overwrites_stale_complete_health(setup, monkeypatch):
    """No old green health survives a failed new boot/source SHA preflight."""
    path, root, _ = setup
    config = svc.load_config(path)
    root.mkdir(mode=0o700)
    svc._health(root, status="TRAINING_CAP_REACHED_NOT_OOS",
                verified=4, run_count=1)
    monkeypatch.setattr(svc, "_digest", lambda _: "incorrect-sha")
    with pytest.raises(ValueError, match="SHA mismatch"):
        svc.serve(config, launcher=lambda *_a, **_kw: pytest.fail("must not spawn"))
    report = json.loads((root / "unattended_research_health.json").read_text())
    assert report["status"] == "FAULT_REQUIRES_EVIDENCE_REVIEW"
    assert report["market_edge_confirmed"] is False
