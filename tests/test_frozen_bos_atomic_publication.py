"""Synthetic atomic publication checks; no original XAUUSD market data."""
from pathlib import Path

import pytest

import scripts.run_bos_fib_frozen_sensitivity as frozen


def _staging_dirs(parent: Path):
    return list(parent.glob(".reports.staging-*"))


def test_failed_later_year_leaves_no_partial_annual_evidence(tmp_path, monkeypatch):
    destination = tmp_path / "reports"

    def fail_on_second_year(source, years, staging):
        assert years == [2012, 2017]
        (staging / "2012").mkdir()
        (staging / "2012" / "summary.json").write_text('{"year": 2012}')
        raise RuntimeError("synthetic 2017 annual replay failed")

    monkeypatch.setattr(frozen, "_execute_unpublished", fail_on_second_year)
    with pytest.raises(RuntimeError, match="2017 annual replay failed"):
        frozen.execute(tmp_path / "not_real_gold.zip", [2012, 2017], destination)
    assert not destination.exists()
    assert _staging_dirs(tmp_path) == []


def test_success_publishes_complete_evidence_and_cleans_stage(tmp_path, monkeypatch):
    destination = tmp_path / "reports"
    expected = {"status": "ACCOUNTING_RECONCILED_NOT_BROKER_CERTIFIED"}

    def success(source, years, staging):
        (staging / "2012").mkdir()
        (staging / "2012" / "summary.json").write_text('{"year": 2012}')
        (staging / "frozen_sensitivity_summary.json").write_text('{"complete": true}')
        assert not destination.exists()
        return expected

    monkeypatch.setattr(frozen, "_execute_unpublished", success)
    assert frozen.execute(tmp_path / "synthetic.zip", [2012], destination) == expected
    assert (destination / "2012" / "summary.json").is_file()
    assert (destination / "frozen_sensitivity_summary.json").is_file()
    assert _staging_dirs(tmp_path) == []


def test_success_replaces_only_an_existing_empty_directory(tmp_path, monkeypatch):
    destination = tmp_path / "reports"
    destination.mkdir()

    def success(source, years, staging):
        (staging / "frozen_sensitivity_summary.json").write_text("complete")
        return {}

    monkeypatch.setattr(frozen, "_execute_unpublished", success)
    frozen.execute(tmp_path / "synthetic.zip", [2012], destination)
    assert (destination / "frozen_sensitivity_summary.json").read_text() == "complete"
    assert _staging_dirs(tmp_path) == []


def test_concurrent_destination_population_is_never_overwritten(tmp_path, monkeypatch):
    destination = tmp_path / "reports"

    def concurrent_writer(source, years, staging):
        (staging / "frozen_sensitivity_summary.json").write_text("new")
        destination.mkdir()
        (destination / "prior.txt").write_text("do not overwrite")
        return {}

    monkeypatch.setattr(frozen, "_execute_unpublished", concurrent_writer)
    with pytest.raises(FileExistsError, match="nonempty"):
        frozen.execute(tmp_path / "synthetic.zip", [2012], destination)
    assert (destination / "prior.txt").read_text() == "do not overwrite"
    assert not (destination / "frozen_sensitivity_summary.json").exists()
    assert _staging_dirs(tmp_path) == []


def test_existing_empty_destination_survives_failed_replay(tmp_path, monkeypatch):
    destination = tmp_path / "reports"
    destination.mkdir()

    def fail(source, years, staging):
        (staging / "2012").mkdir()
        raise ValueError("synthetic source hash changed")

    monkeypatch.setattr(frozen, "_execute_unpublished", fail)
    with pytest.raises(ValueError, match="source hash changed"):
        frozen.execute(tmp_path / "synthetic.zip", [2012], destination)
    assert destination.is_dir()
    assert list(destination.iterdir()) == []
    assert _staging_dirs(tmp_path) == []
