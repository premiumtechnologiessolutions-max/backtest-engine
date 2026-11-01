"""Synthetic-only tests for the REAL-source bootstrap coordinator.

The fake CLI runner exercises orchestration and immutability; it is NOT
original Gold validation or independent OOS evidence.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import bootstrap_arithmetic_training as module


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    gold = tmp_path / "Gold data.zip"
    gold.write_bytes(b"synthetic test placeholder")
    root = tmp_path / "private_bootstrap"
    calls = []
    monkeypatch.setattr(module, "_digest", lambda _: module.SOURCE_SHA)

    def run(command, *, cwd, text, capture_output, timeout, check):
        assert command[:4] == [module.sys.executable, "-m", "norisk_quant.cli",
                               "backtest"]
        assert timeout == 1200
        assert "--all-in-cost-per-ounce" in command
        assert command[command.index("--all-in-cost-per-ounce") + 1] == "0.40"
        assert "--formula-json" in command
        year = int(command[command.index("--start") + 1][:4])
        engine = command[command.index("--execution") + 1]
        out = Path(command[command.index("--out") + 1])
        calls.append((year, engine))
        out.mkdir(parents=True, exist_ok=True)
        summary = {
            "source_fingerprints": {
                "source_file_sha256": module.SOURCE_SHA,
                "loaded_m1_bidask_sha256": "a" * 64,
            },
            "trades_exposed_to_uncertain_gaps": 0,
            "forced_end_of_data_closures": 0,
        }
        (out / "summary.json").write_text(json.dumps(summary))
        (out / "monthly.csv").write_text(
            "period,net_pnl\n" + "".join(
                f"{year}-{month:02d},{10 if month == 1 else -5 if month == 2 else 0}\n"
                for month in range(1, 13)))
        for filename in ("trades.csv", "weekly.csv", "equity_m1.csv",
                         "gap_catalogue.csv"):
            (out / filename).write_text("synthetic fixture only\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", run)
    def verified(reference, fast, *, identity, year):
        assert reference.is_dir() and fast.is_dir()
        assert identity == module.Formula().identity()
        return {
            "trades": 10, "net_usd_per_oz": 5.0, "fees_usd": 4.0,
            "positive_months": 1, "bidask_sha256": "a" * 64,
        }

    monkeypatch.setattr(module, "_compare_outputs", verified)
    return gold, root, calls


def test_seed_uses_audited_years_and_resumes_without_new_replay(sandbox):
    gold, root, calls = sandbox
    first = module.bootstrap(gold, root, years=[2012, 2013], min_free_gb=0)
    assert first["status"] == "REAL_SOURCE_TRAINING_SEED_RECONCILED_NOT_OOS"
    assert calls == [(2012, "reference"), (2012, "fast"),
                     (2013, "reference"), (2013, "fast")]
    assert first["annual_reference_fast_pairs"] == 2
    assert first["positive_months_training"] == 2
    assert first["net_usd_per_oz_training"] == 10.0
    assert first["independent_oos_proven"] is False
    initial = root / "initial_training_input.json"
    original = initial.read_bytes()
    payload = json.loads(original)
    assert payload["years"] == [2012, 2013]
    assert payload["explored_ids"] == []
    assert len(payload["candidates"]) == 1
    assert len(payload["candidates"][0]["records"]) == 2
    second = module.bootstrap(gold, root, years=[2012, 2013], min_free_gb=0)
    assert second == first
    assert initial.read_bytes() == original
    assert len(calls) == 4, "resume must not rerun valid yearly engines"


def test_changed_source_fingerprint_fails_before_seed_republication(sandbox):
    gold, root, _ = sandbox
    module.bootstrap(gold, root, min_free_gb=0)
    seed = root / "initial_training_input.json"
    original = seed.read_bytes()
    report = root / "annual_replays" / "2012" / "reference" / "summary.json"
    data = json.loads(report.read_text())
    data["source_fingerprints"]["source_file_sha256"] = "b" * 64
    report.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="fingerprint"):
        module.bootstrap(gold, root, min_free_gb=0)
    assert seed.read_bytes() == original


def test_rejects_noncanonical_training_year_controls(sandbox):
    gold, root, calls = sandbox
    for years in ([2012], [2013, 2012], [2012, 2012],
                  [2012, True], [2012, 2027], list(range(2010, 2019))):
        with pytest.raises(ValueError, match="years"):
            module.bootstrap(gold, root, years=years, min_free_gb=0)
    assert not root.exists()
    assert not calls


def test_partial_failing_cli_never_publishes_training_seed(sandbox, monkeypatch):
    gold, root, calls = sandbox

    def fail(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="synthetic failure")

    monkeypatch.setattr(module.subprocess, "run", fail)
    with pytest.raises(RuntimeError, match="failed"):
        module.bootstrap(gold, root, min_free_gb=0)
    assert not (root / "initial_training_input.json").exists()
    assert not list(root.glob("annual_replays/*/.*.staging-*"))


def test_refuses_git_checkout_and_symlink_output(sandbox):
    gold, root, calls = sandbox
    root.mkdir()
    (root / ".git").mkdir()
    with pytest.raises(ValueError, match="Git checkout"):
        module.bootstrap(gold, root, min_free_gb=0)
    assert not calls


def test_partial_cli_output_is_never_published(sandbox, monkeypatch):
    gold, root, _ = sandbox

    def interrupted(command, **kwargs):
        out = Path(command[command.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "trades.csv").write_text("partial private report")
        return SimpleNamespace(returncode=1, stdout="", stderr="interrupted")

    monkeypatch.setattr(module.subprocess, "run", interrupted)
    with pytest.raises(RuntimeError, match="no annual evidence was published"):
        module.bootstrap(gold, root, min_free_gb=0)
    assert not (root / "annual_replays" / "2012" / "reference").exists()
    assert not list(root.glob("annual_replays/*/.*.staging-*"))
    assert not (root / "initial_training_input.json").exists()


def test_success_exit_without_complete_report_fails_closed(sandbox, monkeypatch):
    gold, root, _ = sandbox

    def missing_monthly(command, **kwargs):
        out = Path(command[command.index("--out") + 1])
        (out / "summary.json").write_text("{}")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", missing_monthly)
    with pytest.raises(ValueError, match="lacks required evidence"):
        module.bootstrap(gold, root, min_free_gb=0)
    assert not (root / "annual_replays" / "2012" / "reference").exists()
    assert not list(root.glob("annual_replays/*/.*.staging-*"))
    assert not (root / "initial_training_input.json").exists()


def test_relative_private_paths_are_resolved_before_engine_subprocess(sandbox, monkeypatch):
    gold, root, calls = sandbox
    monkeypatch.chdir(gold.parent)
    result = module.bootstrap(Path(gold.name), Path(root.name),
                              years=[2012, 2013], min_free_gb=0)
    assert Path(result["seed"]) == root / "initial_training_input.json"
    assert len(calls) == 4
