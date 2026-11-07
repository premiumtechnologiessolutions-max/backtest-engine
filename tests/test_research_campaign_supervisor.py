"""Synthetic-only campaign supervisor resource, resume and status tests."""
from datetime import datetime, timezone
from hashlib import sha256
import json

import pytest

from scripts import research_campaign_supervisor as supervisor


@pytest.fixture
def job(tmp_path, monkeypatch):
    source = tmp_path / "training_input.json"
    source.write_text("{}", encoding="utf-8")
    gold = tmp_path / "Gold data.zip"
    gold.write_bytes(b"SYNTHETIC PLACEHOLDER, NOT GOLD PRICES")
    root = tmp_path / "campaign"
    calls = []
    monkeypatch.setattr(supervisor, "_digest", lambda _: supervisor.SOURCE_SHA)

    def execute(input_path, data_path, runs, *, seed, first_generation,
                generations, proposal_count, shard_size):
        assert generations == 1
        assert data_path == gold
        calls.append((seed, first_generation, proposal_count))
        folder = runs / f"generation_{first_generation:04d}"
        folder.mkdir()
        next_input = folder / "next_training_input.json"
        payload = json.dumps({
            "schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
            "years": [2012, 2013], "candidates": [{}],
        }).encode()
        next_input.write_bytes(payload)
        proof = {
            "schema": "NRFX_ARITHMETIC_FEEDBACK_EVIDENCE_V1",
            "next_input_sha256": sha256(payload).hexdigest(),
            "original_archive_sha256": supervisor.SOURCE_SHA,
            "training_only": True, "independent_oos_proven": False,
            "live_trading_authorized": False,
            "training_years": [2012, 2013],
        }
        (folder / "next_training_input.json.evidence.json").write_text(
            json.dumps(proof))
        return {"status": "COMPLETE_TRAINING_ONLY_NOT_OOS"}

    monkeypatch.setattr(supervisor, "run_cycles", execute)
    # Fixture fakes annual market replay: the independent actual lineage
    # auditor is tested in test_research_campaign_attestation.py.
    monkeypatch.setattr(
        supervisor, "attest_cached_generation",
        lambda original, folder, *, generation, seed, proposal_count: {
            "next_input_sha256": supervisor._verified_feedback(
                folder / "next_training_input.json")})

    return source, gold, root, calls


def launch(job, **options):
    source, gold, root, _ = job
    defaults = {"seed": 7, "generations": 3, "proposal_count": 2,
                "shard_size": 1, "min_free_gb": 0}
    defaults.update(options)
    return supervisor.campaign(source, gold, root, **defaults)


def test_complete_three_generations_and_idempotent_resume(job):
    first = launch(job)
    assert first["status"] == "COMPLETE_TRAINING_ONLY_NOT_OOS"
    assert [x[1] for x in job[-1]] == [1, 2, 3]
    assert len(first["completed"]) == 3
    assert not first["independent_oos_proven"]
    job[-1].clear()
    second = launch(job)
    assert second["status"] == first["status"]
    assert not job[-1]
    assert all(x["status"] == "REUSED_FULLY_REAUDITED_FEEDBACK" for x in second["completed"])


def test_disk_budget_pauses_without_running(job, monkeypatch):
    from collections import namedtuple
    disk = namedtuple("Disk", "total used free")
    monkeypatch.setattr(supervisor.shutil, "disk_usage",
                        lambda path: disk(1000, 999, 1))
    result = launch(job, min_free_gb=1)
    assert result["status"] == "PAUSED_DISK_BUDGET"
    assert result["completed"] == []
    assert job[-1] == []


def test_feedback_tampering_blocks_resume_and_marks_failure(job):
    launch(job, generations=1)
    proof = job[2] / "cycles" / "generation_0001" / "next_training_input.json.evidence.json"
    data = json.loads(proof.read_text())
    data["independent_oos_proven"] = True
    proof.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="provenance"):
        launch(job, generations=1)
    status = json.loads((job[2] / "campaign_status.json").read_text())
    assert status["status"] == "FAILED_REQUIRES_EVIDENCE_REVIEW"


def test_cycle_failure_releases_campaign_lock_for_resume(job, monkeypatch):
    real = supervisor.run_cycles
    counter = [0]

    def flaky(*args, **kwargs):
        counter[0] += 1
        if counter[0] == 2:
            raise RuntimeError("simulated worker crash")
        return real(*args, **kwargs)

    monkeypatch.setattr(supervisor, "run_cycles", flaky)
    with pytest.raises(RuntimeError, match="worker crash"):
        launch(job)
    assert len(job[-1]) == 1
    monkeypatch.setattr(supervisor, "run_cycles", real)
    resumed = launch(job)
    assert resumed["status"] == "COMPLETE_TRAINING_ONLY_NOT_OOS"
    assert [x[1] for x in job[-1]] == [1, 2, 3]


@pytest.mark.parametrize("override", [
    {"generations": 201}, {"proposal_count": 0}, {"seed": True},
    {"min_free_gb": -1}, {"max_wall_seconds": 0},
])
def test_invalid_resource_limits_fail_without_output(job, override):
    with pytest.raises(ValueError, match="bounded"):
        launch(job, **override)
    assert not job[2].exists()


def test_public_git_checkout_rejected_for_private_campaign(job):
    source, gold, root, calls = job
    root.mkdir()
    (root / ".git").mkdir()
    with pytest.raises(ValueError, match="Git checkout"):
        launch(job)
    assert calls == []


def test_changed_seed_fails_before_reusing_old_annual_results(job):
    launch(job, generations=1)
    before = list(job[-1])
    with pytest.raises(ValueError, match="Immutable campaign intent"):
        launch(job, generations=1, seed=100)
    assert job[-1] == before


def test_changed_initial_training_content_rejected_before_resume(job):
    launch(job, generations=1)
    job[0].write_text('{"changed":true}')
    with pytest.raises(ValueError, match="Immutable campaign intent"):
        launch(job, generations=1)
    assert len(job[-1]) == 1


def test_changed_shard_size_requires_new_campaign_root(job):
    launch(job, generations=1)
    with pytest.raises(ValueError, match="Immutable campaign intent"):
        launch(job, generations=1, shard_size=2)
    assert len(job[-1]) == 1
