"""Synthetic cold storage contract: lossless, private, explicitly reversible."""
from hashlib import sha256
import json

import pytest

from scripts.research_equity_cold_storage import (
    freeze_equity_storage, restore_equity_storage,
)
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA


@pytest.fixture
def generation(tmp_path):
    folder = tmp_path / "generation_0001"
    folder.mkdir()
    source = json.dumps({"schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
                         "years": [2012, 2013], "candidates": [{}]}).encode()
    (folder / "next_training_input.json").write_bytes(source)
    (folder / "next_training_input.json.evidence.json").write_text(json.dumps({
        "schema": "NRFX_ARITHMETIC_FEEDBACK_EVIDENCE_V1",
        "next_input_sha256": sha256(source).hexdigest(),
        "original_archive_sha256": SOURCE_SHA,
        "training_only": True, "independent_oos_proven": False,
        "live_trading_authorized": False,
    }))
    shard = folder / "replay_2012_from_001_count_001"
    shard.mkdir()
    (shard / "training_replay_index.json").write_text(json.dumps({
        "training_only": True, "independent_oos_proven": False,
        "results": [{"relative_dir": "001_abcdef0123456789"}],
    }))
    reports = []
    for mode in ("reference", "fast"):
        report = shard / "001_abcdef0123456789" / mode
        report.mkdir(parents=True)
        path = report / "equity_m1.csv"
        path.write_bytes(b"at,realized,equity\n" +
                         b"2012-01-01T00:01:00Z,0.0,0.0\n" * 10000)
        reports.append(path)
    return folder, reports


def test_lossless_archive_pilot_and_restoration(generation):
    folder, paths = generation
    before = [p.read_bytes() for p in paths]
    result = freeze_equity_storage(folder)
    assert result["file_count"] == 2
    assert result["compressed_bytes"] < result["original_bytes"] / 4
    assert not result["raw_pruned"]
    assert [p.read_bytes() for p in paths] == before
    second = freeze_equity_storage(folder, prune_raw=True)
    assert second["raw_pruned"]
    assert all(not p.exists() for p in paths)
    rehydrated = restore_equity_storage(folder)
    assert rehydrated["restored_files"] == 2
    assert [p.read_bytes() for p in paths] == before
    assert restore_equity_storage(folder)["restored_files"] == 0
    assert not result["independent_oos_proven"]


def test_mutated_compressed_archive_blocks_restore(generation):
    folder, paths = generation
    freeze_equity_storage(folder, prune_raw=True)
    archive = paths[0].with_name("equity_m1.csv.gz")
    with archive.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        restore_equity_storage(folder)


def test_mutated_raw_existing_report_refused(generation):
    folder, paths = generation
    freeze_equity_storage(folder)
    paths[0].write_bytes(b"invalid")
    with pytest.raises(ValueError, match="Existing raw"):
        restore_equity_storage(folder)


def test_incomplete_feedback_blocks_all_archiving(generation):
    folder, paths = generation
    proof = folder / "next_training_input.json.evidence.json"
    data = json.loads(proof.read_text())
    data["independent_oos_proven"] = True
    proof.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Complete audited"):
        freeze_equity_storage(folder)
    assert not any(folder.rglob("*.gz"))


def test_symlink_equity_is_rejected(generation):
    folder, paths = generation
    paths[0].unlink()
    paths[0].symlink_to(paths[1])
    with pytest.raises(ValueError, match="Unsafe"):
        freeze_equity_storage(folder)
