"""Synthetic-only coverage for the complete-generation training feedback bridge.

Mocked report comparisons test orchestration/integrity gates, not historical
Gold ZIP execution, tick parity, profitability, or independent holdout.
"""
from __future__ import annotations

from dataclasses import asdict
import copy
import json
from pathlib import Path

import pytest

from norisk_quant.math_discovery import Formula
from norisk_quant.research_evolution import evolve_training_generation
from scripts import compile_arithmetic_training_feedback as bridge
from scripts.materialize_arithmetic_generation import materialize
from scripts.run_arithmetic_evolution import run


def _training():
    return {
        "schema": bridge.SCHEMA, "years": [2012, 2013], "explored_ids": [],
        "candidates": [{"formula": asdict(Formula()), "records": [
            {"year": year, "metrics": {
                "months": {f"{year}-{month:02d}": 1.0 for month in range(1, 13)},
                "net_usd_per_oz": 12.0, "trades": 45, "fees_usd": 18.0,
                "positive_months": 12, "uncertain_gap_trades": 0,
                "synthetic_forced_closures": 0, "accounting": "PASSED",
            }} for year in (2012, 2013)]}],
    }


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    source = tmp_path / "training.json"
    generation = tmp_path / "generation.json"
    source.write_text(json.dumps(_training()), encoding="utf-8")
    run(source, generation, seed=17, generation=1, proposal_count=2)
    dispatch_dir = tmp_path / "dispatch"
    dispatch = materialize(source, generation, dispatch_dir)
    directories = []
    metrics = {
        "trades": 45, "net_usd_per_oz": 12.0, "fees_usd": 18.0,
        "positive_months": 12, "bidask_sha256": "f" * 64,
    }
    for year in (2012, 2013):
        directory = tmp_path / f"replay-{year}"
        directory.mkdir()
        rows = []
        for proposal in dispatch["formulas"]:
            ordinal, identity = proposal["ordinal"], proposal["identity"]
            name = f"{ordinal:03d}_{identity[:16]}"
            for engine in ("reference", "fast"):
                folder = directory / name / engine
                folder.mkdir(parents=True)
                for filename in bridge.REPORTS:
                    (folder / filename).write_text("synthetic fixture\n", encoding="utf-8")
                (folder / "monthly.csv").write_text(
                    "period,net_pnl\n" + "".join(
                        f"{year}-{month:02d},1.0\n" for month in range(1, 13)),
                    encoding="utf-8")
                (folder / "summary.json").write_text(json.dumps({
                    "source_fingerprints": {
                        "source_file_sha256": bridge.SOURCE_SHA,
                        "loaded_m1_bidask_sha256": "f" * 64,
                    },
                    "trades_exposed_to_uncertain_gaps": 0,
                    "forced_end_of_data_closures": 0,
                }), encoding="utf-8")
            rows.append({
                "ordinal": ordinal, "identity": identity,
                "reference_fast_parity": "PASSED",
                "metrics": metrics.copy(), "relative_dir": name,
            })
        index = {
            "schema": bridge.INDEX_SCHEMA,
            "training_only": True,
            "independent_oos_proven": False,
            "live_trading_authorized": False,
            "data_archive_sha256": bridge.SOURCE_SHA,
            "training_input_sha256": bridge._sha(source),
            "generation_manifest_sha256": dispatch["generation_manifest_sha256"],
            "year": year, "requested_start_ordinal": 1,
            "requested_limit": 2, "completed": 2,
            "all_in_cost_per_ounce": 0.40, "results": rows,
        }
        (directory / "training_replay_index.json").write_text(
            json.dumps(index), encoding="utf-8")
        directories.append(directory)

    calls = []
    def verified_compare(reference, fast, *, identity, year):
        calls.append((identity, year))
        assert reference.is_dir() and fast.is_dir()
        return metrics.copy()
    monkeypatch.setattr(bridge, "_compare_outputs", verified_compare)
    return source, generation, dispatch_dir, directories, tmp_path / "next.json", calls


def _index(directory):
    return directory / "training_replay_index.json"


def _mutate(directory, fn):
    path = _index(directory)
    data = json.loads(path.read_text())
    fn(data)
    path.write_text(json.dumps(data))


def test_complete_feedback_produces_replayable_next_generation(evidence):
    source, generation, dispatch, shards, output, calls = evidence
    first = bridge.compile_feedback(source, generation, dispatch, shards, output)
    assert first["status"] == "COMPLETE_EXPOSED_TRAINING_FEEDBACK_NOT_OOS"
    assert first["evaluated_formulas"] == 2
    assert first["next_candidate_count"] == 3
    assert len(calls) == 4
    next_input = json.loads(output.read_text())
    assert next_input["years"] == [2012, 2013]
    assert len(next_input["explored_ids"]) == 3
    assert len(next_input["candidates"]) == 3
    assert all(len(candidate["records"]) == 2 for candidate in next_input["candidates"])
    next_result = evolve_training_generation(
        next_input["candidates"], tuple(next_input["years"]),
        seed=19, generation=2, proposal_count=2,
        explored_ids=tuple(next_input["explored_ids"]))
    assert len(next_result["proposals"]) == 2
    evidence_doc = json.loads((output.parent / (output.name + ".evidence.json")).read_text())
    assert evidence_doc["complete_formula_year_pairs"] == 4
    assert evidence_doc["independent_oos_proven"] is False
    assert evidence_doc["next_input_sha256"] == bridge._sha(output)
    assert bridge.compile_feedback(source, generation, dispatch, shards[::-1], output) == first


def test_incomplete_training_year_refused_before_output(evidence):
    source, generation, dispatch, shards, output, _ = evidence
    with pytest.raises(ValueError, match="missing training year"):
        bridge.compile_feedback(source, generation, dispatch, shards[:1], output)
    assert not output.exists()


@pytest.mark.parametrize("change", [
    lambda index: index.update({"year": 2027}),
    lambda index: index.update({"data_archive_sha256": "0" * 64}),
    lambda index: index.update({"all_in_cost_per_ounce": 0.41}),
    lambda index: index.update({"training_only": False}),
    lambda index: index.update({"completed": 1}),
    lambda index: index["results"][0].update({"reference_fast_parity": "FAILED"}),
    lambda index: index["results"][0].update({"ordinal": 2}),
    lambda index: index["results"][0]["metrics"].update({"net_usd_per_oz": 100.0}),
    lambda index: index["results"].pop(),
])
def test_replay_index_corruption_rejected(evidence, change):
    source, generation, dispatch, shards, output, _ = evidence
    _mutate(shards[0], change)
    with pytest.raises(ValueError):
        bridge.compile_feedback(source, generation, dispatch, shards, output)
    assert not output.exists()


def test_duplicate_replay_shard_refused(evidence):
    source, generation, dispatch, shards, output, _ = evidence
    with pytest.raises(ValueError, match="Duplicate replay directory"):
        bridge.compile_feedback(source, generation, dispatch, [*shards, shards[0]], output)


def test_wrong_report_archive_fingerprint_refused(evidence):
    source, generation, dispatch, shards, output, _ = evidence
    first = next(shards[0].glob("*/reference/summary.json"))
    summary = json.loads(first.read_text())
    summary["source_fingerprints"]["source_file_sha256"] = "0" * 64
    first.write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="different source archive"):
        bridge.compile_feedback(source, generation, dispatch, shards, output)


def test_noncanonical_monthly_evidence_refused(evidence):
    source, generation, dispatch, shards, output, _ = evidence
    first = next(shards[0].glob("*/reference/monthly.csv"))
    first.write_text(first.read_text().replace("2012-04", "2012-05", 1))
    with pytest.raises(ValueError, match="incomplete monthly"):
        bridge.compile_feedback(source, generation, dispatch, shards, output)


def test_duplicate_formula_year_across_different_shards_refused(evidence, tmp_path):
    source, generation, dispatch, shards, output, _ = evidence
    import shutil
    duplicate = tmp_path / "replay-duplicate"
    shutil.copytree(shards[0], duplicate)
    with pytest.raises(ValueError, match="Duplicate annual formula"):
        bridge.compile_feedback(source, generation, dispatch, [*shards, duplicate], output)


def test_immutable_feedback_rejects_modified_existing_output(evidence):
    source, generation, dispatch, shards, output, _ = evidence
    bridge.compile_feedback(source, generation, dispatch, shards, output)
    output.write_text("{}")
    with pytest.raises(ValueError, match="differs"):
        bridge.compile_feedback(source, generation, dispatch, shards, output)


def test_symlinked_report_rejected_before_comparison(evidence):
    source, generation, dispatch, shards, output, _ = evidence
    report = next(shards[0].glob("*/fast/trades.csv"))
    report.unlink()
    report.symlink_to(source)
    with pytest.raises(ValueError, match="symlinked"):
        bridge.compile_feedback(source, generation, dispatch, shards, output)
