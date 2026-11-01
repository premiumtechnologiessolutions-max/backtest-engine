"""Synthetic success-path tests for frozen annual evidence publication.

These tests prove publication mechanics only; they do not validate real market
data, historical 13-field parity, or a profitable strategy.
"""
import json
from pathlib import Path

import pytest

import scripts.run_bos_fib_frozen_sensitivity as frozen


def test_successful_multiyear_run_publishes_only_complete_staging(tmp_path, monkeypatch):
    destination = tmp_path / "audited"
    source = tmp_path / "synthetic.zip"
    source.write_bytes(b"synthetic fixture")
    staging_paths = []

    def complete_run(gold_zip, years, staging):
        assert gold_zip == source
        assert years == [2012, 2017]
        assert not destination.exists()
        staging_paths.append(staging)
        for year in years:
            year_dir = staging / str(year)
            year_dir.mkdir()
            (year_dir / "summary.json").write_text(
                json.dumps({"year": year, "synthetic": True}), encoding="utf-8"
            )
        return {"years_visited_independently": years, "synthetic": True}

    monkeypatch.setattr(frozen, "_execute_unpublished", complete_run)
    result = frozen.execute(source, [2012, 2017], destination)

    assert result == {"years_visited_independently": [2012, 2017], "synthetic": True}
    assert destination.is_dir()
    assert sorted(p.name for p in destination.iterdir()) == ["2012", "2017"]
    for year in (2012, 2017):
        assert json.loads((destination / str(year) / "summary.json").read_text()) == {
            "year": year, "synthetic": True
        }
    assert len(staging_paths) == 1 and not staging_paths[0].exists()
    assert not list(tmp_path.glob(".audited.staging-*"))


def test_existing_evidence_is_not_replaced_or_deleted(tmp_path, monkeypatch):
    destination = tmp_path / "audited"
    destination.mkdir()
    evidence = destination / "summary.json"
    evidence.write_text('{"preserve":true}', encoding="utf-8")
    called = []

    def forbidden(*args):
        called.append(True)
        raise AssertionError("execution must not start when destination has evidence")

    monkeypatch.setattr(frozen, "_execute_unpublished", forbidden)
    with pytest.raises(FileExistsError, match="nonempty"):
        frozen.execute(tmp_path / "missing.zip", [2012], destination)

    assert not called
    assert evidence.read_text(encoding="utf-8") == '{"preserve":true}'
    assert not list(tmp_path.glob(".audited.staging-*"))
