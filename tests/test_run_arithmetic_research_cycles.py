"""Orchestration tests use synthetic evidence; never claim original Gold replay."""
import json

import pytest

from scripts import run_arithmetic_research_cycles as cycles


@pytest.fixture
def harness(tmp_path, monkeypatch):
    source = tmp_path / "training.json"
    source.write_text(json.dumps({"schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1", "candidates": []}), encoding="utf-8")
    gold = tmp_path / "Gold data.zip"
    gold.write_bytes(b"fixture-not-market-data")
    output = tmp_path / "research"
    calls = []
    monkeypatch.setattr(cycles, "_digest", lambda path: cycles.SOURCE_SHA)

    def generate(inp, manifest, *, seed, generation, proposal_count):
        calls.append(("generate", generation, seed, inp.name))
        if not manifest.exists():
            manifest.write_text(json.dumps({"generation": generation}), encoding="utf-8")

    def dispatch(inp, manifest, directory):
        directory.mkdir(exist_ok=True)
        return {"training_years": [2012, 2013], "formula_count": 3,
                "training_input_sha256": "frozen"}

    def replay(inp, manifest, directory, archive, archive_sha, year, dest, *,
               start_ordinal, limit):
        calls.append(("replay", year, start_ordinal, limit))
        dest.mkdir()
        (dest / "training_replay_index.json").write_text(
            json.dumps({"year": year, "requested_start_ordinal": start_ordinal,
                        "requested_limit": limit, "results": [{}] * limit}),
            encoding="utf-8")

    def feedback(inp, manifest, directory, shards, next_input):
        calls.append(("feedback", len(shards)))
        if not next_input.exists():
            next_input.write_text(json.dumps({"schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1", "candidates": []}), encoding="utf-8")
        return {"status": "COMPLETE_EXPOSED_TRAINING_FEEDBACK_NOT_OOS",
                "next_input_sha256": "b" * 64}

    monkeypatch.setattr(cycles, "generate", generate)
    monkeypatch.setattr(cycles, "materialize", dispatch)
    monkeypatch.setattr(cycles, "replay", replay)
    monkeypatch.setattr(cycles, "compile_feedback", feedback)
    monkeypatch.setattr(cycles, "_load_strict",
                        lambda p: (json.loads(p.read_text()), "frozen"))
    monkeypatch.setattr(cycles, "_checked_index",
                        lambda idx, dispatch, years, digest:
                        (idx["year"], idx["results"]))
    return source, gold, output, calls


def run(harness, **kwargs):
    source, gold, output, _ = harness
    options = {"seed": 10, "first_generation": 1, "generations": 1,
               "proposal_count": 3, "shard_size": 2}
    options.update(kwargs)
    return cycles.run_cycles(source, gold, output, **options)


def test_two_generations_execute_all_shards_and_feed_next_input(harness):
    result = run(harness, generations=2)
    calls = harness[-1]
    assert result["status"] == "COMPLETE_TRAINING_ONLY_NOT_OOS"
    assert [c[1:3] for c in calls if c[0] == "generate"] == [(1, 10), (2, 11)]
    assert len([c for c in calls if c[0] == "replay"]) == 8
    assert len([c for c in calls if c[0] == "feedback"]) == 2
    assert result["independent_oos_proven"] is False
    assert result["live_trading_authorized"] is False


def test_resume_does_not_rerun_completed_shards(harness):
    run(harness)
    harness[-1].clear()
    run(harness)
    assert not [c for c in harness[-1] if c[0] == "replay"]
    assert len([c for c in harness[-1] if c[0] == "feedback"]) == 1


def test_corrupt_resume_shard_fails_closed(harness):
    run(harness)
    bad = harness[2] / "generation_0001" / "replay_2012_from_001_count_002"
    (bad / "training_replay_index.json").write_text("{}", encoding="utf-8")
    with pytest.raises(KeyError):
        run(harness)


@pytest.mark.parametrize("changed", [
    {"generations": 11}, {"proposal_count": 0}, {"shard_size": 129},
    {"seed": True}, {"first_generation": 0},
])
def test_invalid_controls_refused_before_write(harness, changed):
    with pytest.raises(ValueError, match="bounded integer"):
        run(harness, **changed)
    assert not harness[2].exists()


def test_wrong_original_zip_refused_before_write(harness, monkeypatch):
    monkeypatch.setattr(cycles, "_digest", lambda p: "0" * 64)
    with pytest.raises(ValueError, match="authorized original"):
        run(harness)
    assert not harness[2].exists()


def test_symlink_output_refused_before_write(harness):
    harness[2].symlink_to(harness[0].parent, target_is_directory=True)
    with pytest.raises(ValueError, match="directory"):
        run(harness)


def test_active_output_writer_blocks_before_generation(harness):
    output = harness[2]
    output.mkdir()
    with cycles._exclusive_research_lock(output):
        with pytest.raises(ValueError, match="already running"):
            run(harness)
        assert not (output / "generation_0001").exists()
        assert not harness[-1]
    assert run(harness)["status"] == "COMPLETE_TRAINING_ONLY_NOT_OOS"


def test_failed_cycle_releases_kernel_lock_for_safe_resume(harness, monkeypatch):
    original = cycles.generate

    def interrupted(*args, **kwargs):
        raise RuntimeError("simulated interrupted generation")

    monkeypatch.setattr(cycles, "generate", interrupted)
    with pytest.raises(RuntimeError, match="interrupted"):
        run(harness)
    monkeypatch.setattr(cycles, "generate", original)
    assert run(harness)["status"] == "COMPLETE_TRAINING_ONLY_NOT_OOS"


def test_symlink_lock_file_rejected_without_generation(harness):
    output = harness[2]
    output.mkdir()
    (output / ".research_batch.lock").symlink_to(harness[0])
    with pytest.raises(ValueError, match="Unsafe batch lock symlink"):
        run(harness)
    assert not (output / "generation_0001").exists()


def test_nonregular_lock_file_rejected_without_generation(harness):
    output = harness[2]
    output.mkdir()
    (output / ".research_batch.lock").mkdir()
    with pytest.raises((ValueError, OSError)):
        run(harness)
    assert not (output / "generation_0001").exists()


def test_world_readable_existing_lock_rejected(harness):
    output = harness[2]
    output.mkdir()
    lock = output / ".research_batch.lock"
    lock.write_text("untrusted", encoding="utf-8")
    lock.chmod(0o644)
    with pytest.raises(ValueError, match="Unsafe batch lock file"):
        run(harness)
    assert not (output / "generation_0001").exists()


def test_candidate_budget_preflight_rejects_invalid_active_pool(harness):
    source, gold, root, calls = harness
    source.write_text(json.dumps({
        "schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
        "candidates": [{}] * 129,
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="Active training candidate"):
        run(harness, proposal_count=2)
    assert not (root / "generation_0001").exists()
    assert calls == []


def test_private_output_directory_inside_git_checkout_is_forbidden(harness, tmp_path):
    source, gold, _, calls = harness
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".git").mkdir()
    with pytest.raises(ValueError, match="Git checkout"):
        cycles.run_cycles(source, gold, checkout / "private-research",
                          seed=7, first_generation=1, generations=1,
                          proposal_count=2)
    assert not (checkout / "private-research").exists()
    assert calls == []


def test_candidate_budget_checked_again_before_second_generation(harness, monkeypatch):
    # Simulated first-generation feedback can exceed the frozen 128-candidate
    # input bound. The second generation must not run any formula replays.
    real_feedback = cycles.compile_feedback
    seen = []

    def full_feedback(inp, manifest, directory, shards, next_input):
        result = real_feedback(inp, manifest, directory, shards, next_input)
        source = json.loads(next_input.read_text())
        source["candidates"] = [{}] * 129
        next_input.write_text(json.dumps(source), encoding="utf-8")
        seen.append(next_input)
        return result

    monkeypatch.setattr(cycles, "compile_feedback", full_feedback)
    with pytest.raises(ValueError, match="Active training candidate"):
        run(harness, generations=2)
    assert len(seen) == 1
    assert not (harness[2] / "generation_0002").exists()
