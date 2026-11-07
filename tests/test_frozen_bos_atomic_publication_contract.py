"""Fail-closed publication tests for the frozen annual replay.

Synthetic fixtures only. No private Gold archive or historical parity claim.
"""
from pathlib import Path

import pytest

import scripts.run_bos_fib_frozen_sensitivity as frozen


def test_later_year_failure_never_publishes_partial_annual_evidence(tmp_path, monkeypatch):
    destination = tmp_path / "audited"
    source = tmp_path / "synthetic.zip"
    source.write_bytes(b"synthetic only")
    seen = []

    def fail_after_partial_work(gold_zip, years, staging):
        assert gold_zip == source
        assert years == [2012, 2017]
        assert staging.parent == destination.parent
        assert staging != destination
        (staging / "2012").mkdir()
        (staging / "2012" / "summary.json").write_text('{"fake":true}')
        seen.append(staging)
        raise RuntimeError("synthetic second-year execution failed")

    monkeypatch.setattr(frozen, "_execute_unpublished", fail_after_partial_work)
    with pytest.raises(RuntimeError, match="second-year"):
        frozen.execute(source, [2012, 2017], destination)

    assert len(seen) == 1
    assert not seen[0].exists(), "failed staging directory must be removed"
    assert not destination.exists(), "partial annual evidence must never be published"


def test_concurrent_destination_population_blocks_publication(tmp_path, monkeypatch):
    destination = tmp_path / "audited"
    source = tmp_path / "synthetic.zip"
    source.write_bytes(b"synthetic only")
    staged = []

    def simulate_concurrent_writer(gold_zip, years, staging):
        (staging / "frozen_sensitivity_summary.json").write_text('{"synthetic":true}')
        staged.append(staging)
        destination.mkdir()
        (destination / "owner.txt").write_text("do not overwrite", encoding="utf-8")
        return {"status": "synthetic"}

    monkeypatch.setattr(frozen, "_execute_unpublished", simulate_concurrent_writer)
    with pytest.raises(FileExistsError, match="nonempty"):
        frozen.execute(source, [2012], destination)

    assert (destination / "owner.txt").read_text(encoding="utf-8") == "do not overwrite"
    assert not (destination / "frozen_sensitivity_summary.json").exists()
    assert staged and not staged[0].exists()
