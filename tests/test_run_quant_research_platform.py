"""Synthetic orchestration contracts; NOT historical market/OOS certification."""
import json
import os
from pathlib import Path

import pytest

from scripts import run_quant_research_platform as module


@pytest.fixture
def harness(tmp_path, monkeypatch):
    gold = tmp_path / "Gold data.zip"
    gold.write_bytes(b"SYNTHETIC ONLY")
    root = tmp_path / "quant_platform"
    calls = []
    monkeypatch.setattr(module, "_digest", lambda path: module.SOURCE_SHA)

    def fake_bootstrap(source, destination, *, years, min_free_gb):
        calls.append(("bootstrap", list(years)))
        assert source == gold and destination == root / "bootstrap"
        destination.mkdir(parents=True, exist_ok=True)
        seed = destination / "initial_training_input.json"
        seed.write_text("synthetic research seed")
        return {"status": "REAL_SOURCE_TRAINING_SEED_RECONCILED_NOT_OOS",
                "seed": str(seed), "training_only": True}

    def fake_campaign_impl(input_path, source, destination, *, seed,
                           generations, proposal_count, shard_size, min_free_gb,
                           max_wall_seconds, proposal_policy):
        calls.append(("campaign", generations, proposal_count, proposal_policy))
        assert input_path.is_file() and source == gold
        assert destination == root / "campaign"
        (destination / "cycles").mkdir(parents=True, exist_ok=True)
        return {"status": "COMPLETE_TRAINING_ONLY_NOT_OOS",
                "completed": [{"generation": 1, "status": "EXECUTED_AND_VERIFIED_FEEDBACK"}]}

    def fake_dashboard(cycles, output):
        calls.append(("dashboard", output.name))
        assert cycles == root / "campaign" / "cycles"
        assert output == root / "quant_research_dashboard.html"
        output.write_text("synthetic verified dashboard")
        return {"generations": 1, "verified_generations": 1,
                "sha256": "a" * 64, "independent_oos_proven": False}

    monkeypatch.setattr(module, "bootstrap", fake_bootstrap)
    monkeypatch.setattr(module, "campaign", fake_campaign_impl)
    monkeypatch.setattr(module, "build_dashboard", fake_dashboard)
    return gold, root, calls


def _execute(harness, **kwargs):
    gold, root, _ = harness
    options = {"years": [2012, 2013], "seed": 7,
               "generations": 1, "proposal_count": 2,
               "shard_size": 1, "min_free_gb": 0}
    options.update(kwargs)
    return module.run_pipeline(gold, root, **options)


def test_integrates_source_seed_campaign_and_dashboard(harness):
    state = _execute(harness)
    assert state["status"] == "COMPLETE_EXPOSED_TRAINING_PIPELINE_NOT_OOS"
    assert harness[2] == [("bootstrap", [2012, 2013]),
                          ("campaign", 1, 2, "legacy_random"),
                          ("dashboard", "quant_research_dashboard.html")]
    assert state["training_only"] is True
    assert state["independent_oos_proven"] is False
    assert state["live_trading_authorized"] is False
    assert state["dashboard"]["verified_generations"] == 1
    assert json.loads((harness[1] / "platform_status.json").read_text()) == state
    if os.name == "posix":
        assert harness[1].stat().st_mode & 0o077 == 0


def test_paused_campaign_never_fabricates_dashboard(harness, monkeypatch):
    def paused(*args, **kwargs):
        return {"status": "PAUSED_DISK_BUDGET", "completed": []}
    monkeypatch.setattr(module, "campaign", paused)
    state = _execute(harness)
    assert state["status"] == "PAUSED_EXPOSED_TRAINING_PIPELINE_NOT_OOS"
    assert state["dashboard"] is None
    assert not (harness[1] / "quant_research_dashboard.html").exists()


def test_campaign_failure_is_durable_and_never_marked_complete(harness, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("synthetic research failure, no real quotes")
    monkeypatch.setattr(module, "campaign", fail)
    with pytest.raises(RuntimeError, match="research failure"):
        _execute(harness)
    status = json.loads((harness[1] / "platform_status.json").read_text())
    assert status["status"] == "FAILED_REQUIRES_EVIDENCE_REVIEW"
    assert status["error_type"] == "RuntimeError"
    assert "error" not in status
    assert not (harness[1] / "quant_research_dashboard.html").exists()


@pytest.mark.parametrize("options", [
    {"years": [2012]}, {"years": [2013, 2012]},
    {"generations": True}, {"generations": 201},
    {"proposal_count": 0}, {"seed": True},
    {"max_wall_seconds": 0}, {"min_free_gb": -1},
])
def test_invalid_controls_create_no_output(harness, options):
    with pytest.raises(ValueError):
        _execute(harness, **options)
    assert not harness[1].exists()
    assert harness[2] == []


def test_refuses_public_checkout_for_private_results(harness):
    harness[1].mkdir()
    (harness[1] / ".git").mkdir()
    with pytest.raises(ValueError, match="Git checkout"):
        _execute(harness)
    assert not harness[2]


def test_forged_source_zip_is_rejected_before_creating_output(harness, monkeypatch):
    monkeypatch.setattr(module, "_digest", lambda _: "0" * 64)
    with pytest.raises(ValueError, match="SHA-pinned"):
        _execute(harness)
    assert not harness[1].exists()


def test_relative_cli_paths_are_pinned_to_original_directory(harness, monkeypatch):
    gold, root, calls = harness
    monkeypatch.chdir(gold.parent)
    result = module.run_pipeline(Path(gold.name), Path(root.name),
                                 years=[2012, 2013], seed=7,
                                 generations=1, proposal_count=2,
                                 shard_size=1, min_free_gb=0)
    assert result["status"] == "COMPLETE_EXPOSED_TRAINING_PIPELINE_NOT_OOS"
    assert calls[0] == ("bootstrap", [2012, 2013])


def test_rejects_unverified_dashboard_even_when_campaign_claims_complete(
        harness, monkeypatch):
    def false_dashboard(cycles, output):
        output.write_text("unverified UI")
        return {"generations": 1, "verified_generations": 0,
                "sha256": "a" * 64}

    monkeypatch.setattr(module, "build_dashboard", false_dashboard)
    with pytest.raises(ValueError, match="unverified generations"):
        _execute(harness)
    status = json.loads((harness[1] / "platform_status.json").read_text())
    assert status["status"] == "FAILED_REQUIRES_EVIDENCE_REVIEW"


def test_rejects_forged_campaign_completion_without_generations(
        harness, monkeypatch):
    monkeypatch.setattr(
        module, "campaign", lambda *args, **kwargs: {
            "status": "COMPLETE_TRAINING_ONLY_NOT_OOS", "completed": []})
    with pytest.raises(ValueError, match="empty completed"):
        _execute(harness)
    status = json.loads((harness[1] / "platform_status.json").read_text())
    assert status["status"] == "FAILED_REQUIRES_EVIDENCE_REVIEW"
