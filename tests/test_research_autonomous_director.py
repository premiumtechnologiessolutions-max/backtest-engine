"""Synthetic director contracts. NOT a Gold ZIP replay or OOS evidence."""
import json

import pytest

from scripts import research_autonomous_director as director


@pytest.fixture
def env(tmp_path, monkeypatch):
    gold = tmp_path / "Gold data.zip"
    gold.write_bytes(b"SYNTHETIC PRIVATE SOURCE PLACEHOLDER")
    output = tmp_path / "private_research"
    monkeypatch.setattr(director, "_digest", lambda _path: director.SOURCE_SHA)
    return gold, output, monkeypatch


def fake_success(root, calls):
    def run(source, output, *, years, seed, generations, proposal_count,
            shard_size, min_free_gb, max_wall_seconds, proposal_policy):
        assert proposal_policy == "matched_guided_v1"
        assert years == [2012, 2013] and seed == 42
        assert source.is_file() and output == root
        calls.append(generations)
        cycles = root / "campaign" / "cycles"
        for i in range(1, generations + 1):
            folder = cycles / f"generation_{i:04d}"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "next_training_input.json").write_text(
                "synthetic complete hint, NOT authenticated evidence")
        return {
            "status": "COMPLETE_EXPOSED_TRAINING_PIPELINE_NOT_OOS",
            "campaign": {"status": "COMPLETE_TRAINING_ONLY_NOT_OOS",
                         "completed": [{"generation": n} for n in range(1, generations+1)]},
            "dashboard": {"verified_generations": generations},
        }
    return run


def launch(env, **kwargs):
    gold, root, _ = env
    args = dict(years=[2012, 2013], seed=42, target_generations=5,
                step_generations=2, min_free_gb=0,
                max_batch_wall_seconds=60, max_total_wall_seconds=60)
    args.update(kwargs)
    return director.drive(gold, root, **args)


def test_self_advances_guided_generations_and_persists_status(env):
    calls = []
    env[2].setattr(director, "run_pipeline", fake_success(env[1], calls))
    report = launch(env)
    assert calls == [2, 4, 5]
    assert report["status"] == "COMPLETE_HISTORICAL_TRAINING_ONLY_NOT_OOS"
    assert report["verified_generations"] == 5
    assert report["attempts"] == 3
    assert report["proposal_policy"] == "matched_guided_v1"
    assert report["independent_oos_proven"] is False
    assert report["market_edge_confirmed"] is False
    assert report["live_trading_authorized"] is False
    persisted = json.loads((env[1] / "autonomous_research_status.json").read_text())
    assert persisted == report
    assert "Gold data.zip" not in json.dumps(persisted)


def test_restart_uses_existing_generations_as_hint_only(env):
    calls = []
    env[2].setattr(director, "run_pipeline", fake_success(env[1], calls))
    assert launch(env)["verified_generations"] == 5
    calls.clear()
    # Still replays the authenticated platform on restart; it does not
    # trust the director checkpoint alone.
    again = launch(env)
    assert calls == [5]
    assert again["verified_generations"] == 5


def test_paused_time_progress_resumes_without_manual_prompt(env):
    calls = []
    def time_then_success(*args, **kwargs):
        target = kwargs["generations"]
        calls.append(target)
        if len(calls) == 1:
            return {
                "status": "PAUSED_EXPOSED_TRAINING_PIPELINE_NOT_OOS",
                "campaign": {"status": "PAUSED_TIME_BUDGET_BETWEEN_GENERATIONS",
                             "completed": [{"generation": 1}]},
                "dashboard": {"verified_generations": 1},
            }
        return {
            "status": "COMPLETE_EXPOSED_TRAINING_PIPELINE_NOT_OOS",
            "campaign": {"status": "COMPLETE_TRAINING_ONLY_NOT_OOS",
                         "completed": [{"generation": i}
                                       for i in range(1, target + 1)]},
            "dashboard": {"verified_generations": target},
        }
    env[2].setattr(director, "run_pipeline", time_then_success)
    report = launch(env)
    assert calls == [2, 2, 4, 5]
    assert report["status"].startswith("COMPLETE_")


def test_no_progress_pauses_instead_of_spin(env):
    calls = []
    def paused(*args, **kwargs):
        calls.append(1)
        return {"status": "PAUSED_EXPOSED_TRAINING_PIPELINE_NOT_OOS",
                "campaign": {"status": "PAUSED_TIME_BUDGET_BETWEEN_GENERATIONS",
                             "completed": []}, "dashboard": None}
    env[2].setattr(director, "run_pipeline", paused)
    report = launch(env)
    assert report["status"] == "PAUSED_NO_GENERATION_PROGRESS"
    assert calls == [1]


def test_disk_pause_never_promoted_to_success(env):
    env[2].setattr(
        director, "run_pipeline",
        lambda *a, **kw: {
            "status": "PAUSED_EXPOSED_TRAINING_PIPELINE_NOT_OOS",
            "campaign": {"status": "PAUSED_DISK_BUDGET", "completed": []},
            "dashboard": None,
        })
    result = launch(env)
    assert result["status"] == "PAUSED_DISK_BUDGET"


def test_forged_completeness_fails_closed(env):
    env[2].setattr(
        director, "run_pipeline",
        lambda *a, **kw: {
            "status": "COMPLETE_EXPOSED_TRAINING_PIPELINE_NOT_OOS",
            "campaign": {"status": "COMPLETE_TRAINING_ONLY_NOT_OOS",
                         "completed": [{"generation": 1}]},
            "dashboard": {"verified_generations": 1},
        })
    with pytest.raises(ValueError, match="incomplete target"):
        launch(env)
    checkpoint = json.loads(
        (env[1] / "autonomous_research_status.json").read_text())
    assert checkpoint["status"] == "FAILED_REQUIRES_EVIDENCE_REVIEW"


def test_dashboard_claim_without_reconciliation_rejected(env):
    env[2].setattr(
        director, "run_pipeline",
        lambda *a, **kw: {
            "status": "COMPLETE_EXPOSED_TRAINING_PIPELINE_NOT_OOS",
            "campaign": {"status": "COMPLETE_TRAINING_ONLY_NOT_OOS",
                         "completed": [{"generation": 1}, {"generation": 2}]},
            "dashboard": {"verified_generations": 1},
        })
    with pytest.raises(ValueError, match="unaudited dashboard"):
        launch(env)


@pytest.mark.parametrize("options", [
    {"target_generations": 201},
    {"step_generations": 0},
    {"seed": True},
    {"max_resume_attempts": 0},
    {"max_batch_wall_seconds": 3},
    {"years": [2012]},
])
def test_bad_controls_do_not_start_run(env, options):
    with pytest.raises(ValueError):
        launch(env, **options)
    assert not env[1].exists()


def test_source_hash_rejected_before_output(env):
    env[2].setattr(director, "_digest", lambda _: "f" * 64)
    with pytest.raises(ValueError, match="SHA-pinned"):
        launch(env)
    assert not env[1].exists()


def test_existing_target_smaller_than_campaign_is_rejected(env):
    calls = []
    env[2].setattr(director, "run_pipeline", fake_success(env[1], calls))
    launch(env)
    calls.clear()
    with pytest.raises(ValueError, match="Target smaller"):
        launch(env, target_generations=4)
    assert calls == []
