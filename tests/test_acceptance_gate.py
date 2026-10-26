"""Acceptance gate is fail-closed; synthetic tests never access private gold."""
from pathlib import Path

import pytest

from scripts import acceptance_gate as gate


@pytest.fixture
def safe_environment(monkeypatch):
    monkeypatch.setattr(gate, "check_pins", lambda: {"python": "3.12", "packages": gate.PINNED})
    monkeypatch.setattr(
        gate, "command_step",
        lambda name, argv: {
            "name": name, "status": "PASSED", "exit_code": 0,
            "stdout_tail": "a" * 40 if name == "git_revision" else "",
        },
    )


def test_no_private_inputs_cannot_pass(safe_environment):
    result, code = gate.acceptance(gold_zip=None, reference_root=None, years=[2012])
    assert code == 2
    assert result["status"] == "BLOCKED_PRIVATE_ARCHIVE_AND_REFERENCE_NOT_PROVIDED"
    assert [s["name"] for s in result["steps"]] == [
        "pinned_environment", "git_revision", "git_clean", "compile", "pip_check", "full_pytest", "cli_smoke",
    ]


def test_failed_full_pytest_prevents_parity_claim(monkeypatch, safe_environment):
    def fail_pytest(name, argv):
        return {
            "name": name, "status": "FAILED" if name == "full_pytest" else "PASSED",
            "stdout_tail": "a" * 40 if name == "git_revision" else "",
        }
    monkeypatch.setattr(gate, "command_step", fail_pytest)
    result, code = gate.acceptance(gold_zip=None, reference_root=None, years=[2012])
    assert code == 1
    assert result["status"] == "FAILED"
    assert "cli_smoke" not in [s["name"] for s in result["steps"]]


def test_missing_reference_does_not_claim_pass(safe_environment, tmp_path):
    archive = tmp_path / "Gold data.zip"
    archive.write_bytes(b"synthetic only")
    result, code = gate.acceptance(
        gold_zip=archive, reference_root=tmp_path / "not_present", years=[2012],
    )
    assert code == 2
    assert result["status"] == "BLOCKED_PRIVATE_ARCHIVE_OR_REFERENCE_MISSING"


@pytest.mark.parametrize("years", [[], [2012, 2012], [True], [2012.5], [2001]])
def test_invalid_years_fail_before_running_commands(monkeypatch, safe_environment, years):
    def unexpected(*args, **kwargs):
        raise AssertionError("No command should run for invalid years")
    monkeypatch.setattr(gate, "command_step", unexpected)
    result, code = gate.acceptance(gold_zip=None, reference_root=None, years=years)
    assert code == 1
    assert result["status"] == "FAILED"


def test_unpaired_source_flags_fail_before_running_commands(monkeypatch, safe_environment, tmp_path):
    def unexpected(*args, **kwargs):
        raise AssertionError("No command should run for unpaired inputs")
    monkeypatch.setattr(gate, "command_step", unexpected)
    result, code = gate.acceptance(gold_zip=tmp_path / "Gold data.zip",
                                   reference_root=None, years=[2012])
    assert code == 1
    assert result["status"] == "FAILED"


def test_2012_replay_requires_689_trades(safe_environment, tmp_path, monkeypatch):
    import scripts.verify_bos_h1_parity as parity

    source = tmp_path / "Gold data.zip"
    source.write_bytes(b"synthetic only")
    archive = tmp_path / "reference"
    archive.mkdir()

    def fake_verify(gold_zip, reference_root, years):
        return {
            "status": "PASSED", "source_sha256": gate.MARKET_SHA256,
            "fields_per_trade": 13, "scenarios_verified": 2,
            "trades_matched": 688,
        }
    monkeypatch.setattr(parity, "verify", fake_verify)
    result, code = gate.acceptance(gold_zip=source, reference_root=archive, years=[2012])
    assert code == 1
    assert result["status"] == "FAILED"
    assert "689" in result["error"]


def test_valid_2012_replay_contract_passes_research_gate_only(safe_environment, tmp_path, monkeypatch):
    import scripts.verify_bos_h1_parity as parity

    source = tmp_path / "Gold data.zip"
    source.write_bytes(b"synthetic only")
    archive = tmp_path / "reference"
    archive.mkdir()

    def fake_verify(gold_zip, reference_root, years):
        return {
            "status": "PASSED", "source_sha256": gate.MARKET_SHA256,
            "fields_per_trade": 13, "scenarios_verified": 2,
            "trades_matched": 689,
        }
    monkeypatch.setattr(parity, "verify", fake_verify)
    result, code = gate.acceptance(gold_zip=source, reference_root=archive, years=[2012])
    assert code == 0
    assert result["status"] == "PASSED_RESEARCH_GATE_NOT_BROKER_CERTIFIED"
    assert result["broker_tick_fill_certified"] is False
    assert result["clean_out_of_sample_certified"] is False

def test_git_clean_rejects_untracked_source_even_with_zero_exit(monkeypatch):
    # git diff --quiet HEAD misses new untracked source modules. Git status
    # exits 0 for a dirty checkout, so its porcelain output must be checked.
    from types import SimpleNamespace

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="?? src/norisk_quant/new_module.py\\n", stderr="")

    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    step = gate.command_step("git_clean", ["git", "status", "--porcelain=v1", "--untracked-files=all"])
    assert step["status"] == "FAILED"
    assert step["exit_code"] == 0
    assert "new_module.py" in step["stdout_tail"]


def test_git_clean_accepts_clean_porcelain_status(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        gate.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    step = gate.command_step("git_clean", ["git", "status", "--porcelain=v1", "--untracked-files=all"])
    assert step["status"] == "PASSED"


def test_git_clean_rejects_tracked_modification_even_with_zero_exit(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        gate.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=" M src/norisk_quant/data.py\\n", stderr=""),
    )
    step = gate.command_step("git_clean", ["git", "status", "--porcelain=v1", "--untracked-files=all"])
    assert step["status"] == "FAILED"

@pytest.mark.parametrize("failure", ["head_moved", "untracked_after_replay"])
def test_successful_parity_cannot_certify_mutated_checkout(
    safe_environment, tmp_path, monkeypatch, failure,
):
    import scripts.verify_bos_h1_parity as parity

    source = tmp_path / "Gold data.zip"
    source.write_bytes(b"synthetic only")
    archive = tmp_path / "reference"
    archive.mkdir()
    monkeypatch.setattr(parity, "verify", lambda *args: {
        "status": "PASSED", "source_sha256": gate.MARKET_SHA256,
        "fields_per_trade": 13, "scenarios_verified": 2,
        "trades_matched": 689,
    })
    calls = {"git_revision": 0, "git_clean": 0}

    def fake_step(name, argv):
        if name in calls:
            calls[name] += 1
        sha = "a" * 40
        if name == "git_revision" and calls[name] > 1 and failure == "head_moved":
            sha = "b" * 40
        status = "PASSED"
        if name == "git_clean" and calls[name] > 1 and failure == "untracked_after_replay":
            status = "FAILED"
        return {
            "name": name, "status": status, "exit_code": 0,
            "stdout_tail": sha if name == "git_revision" else "",
        }

    monkeypatch.setattr(gate, "command_step", fake_step)
    report, code = gate.acceptance(gold_zip=source, reference_root=archive, years=[2012])
    assert code == 1
    assert report["status"] == "FAILED"
    assert "during acceptance replay" in report["error"]
    assert calls["git_revision"] == 2
    if failure == "untracked_after_replay":
        assert calls["git_clean"] == 2
