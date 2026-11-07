"""Real evolution/dispatch/feedback wiring with SYNTHETIC replay trees.

Only annual engine execution and its reference/fast report comparator are
stubbed. This never tests the original Gold ZIP, broker ticks, or an edge.
"""
from dataclasses import asdict
import json

import pytest

from norisk_quant.math_discovery import Formula
from scripts import run_arithmetic_research_cycles as cycles
from scripts import compile_arithmetic_training_feedback as bridge
from scripts.materialize_arithmetic_generation import materialize


def _initial_training():
    return {
        "schema": "NRFX_ARITHMETIC_TRAINING_INPUT_V1",
        "years": [2012, 2013], "explored_ids": [],
        "candidates": [{
            "formula": asdict(Formula()),
            "records": [
                {"year": year, "metrics": {
                    "months": {f"{year}-{m:02d}": 1.0 for m in range(1, 13)},
                    "net_usd_per_oz": 12.0, "trades": 45, "fees_usd": 18.0,
                    "positive_months": 12, "uncertain_gap_trades": 0,
                    "synthetic_forced_closures": 0, "accounting": "PASSED",
                }} for year in (2012, 2013)
            ],
        }],
    }


@pytest.fixture
def integrated(tmp_path, monkeypatch):
    source = tmp_path / "training.json"
    source.write_text(json.dumps(_initial_training()), encoding="utf-8")
    archive = tmp_path / "Gold data.zip"
    archive.write_bytes(b"SYNTHETIC ZIP PLACEHOLDER, NOT MARKET DATA")
    root = tmp_path / "generations"
    fake_metrics = {
        "trades": 45, "net_usd_per_oz": 12.0, "fees_usd": 18.0,
        "positive_months": 12, "bidask_sha256": "f" * 64,
    }
    calls = []

    # The real market-source SHA precondition cannot be met by a fixture.
    # Override ONLY that gate and the actual data/backtest/reconciliation
    # boundary. Evolution, immutable dispatch, feedback, and evidence output
    # all run with their real implementations.
    monkeypatch.setattr(cycles, "_digest", lambda _: cycles.SOURCE_SHA)
    monkeypatch.setattr(bridge, "_compare_outputs",
                        lambda reference, fast, *, identity, year:
                        fake_metrics.copy())

    def synthetic_replay(training_input, generation_manifest, dispatch_dir,
                         data, source_sha256, year, destination, *,
                         start_ordinal, limit):
        assert source_sha256 == cycles.SOURCE_SHA
        assert year in (2012, 2013)
        dispatch = materialize(training_input, generation_manifest, dispatch_dir)
        entries = dispatch["formulas"][start_ordinal - 1:start_ordinal - 1 + limit]
        destination.mkdir()
        rows = []
        for proposal in entries:
            ordinal, identity = proposal["ordinal"], proposal["identity"]
            folder = destination / f"{ordinal:03d}_{identity[:16]}"
            for engine in ("reference", "fast"):
                report = folder / engine
                report.mkdir(parents=True)
                for filename in bridge.REPORTS:
                    (report / filename).write_text("synthetic fixture only\n",
                                                   encoding="utf-8")
                (report / "monthly.csv").write_text(
                    "period,net_pnl\n" + "".join(
                        f"{year}-{m:02d},1.0\n" for m in range(1, 13)),
                    encoding="utf-8")
                (report / "summary.json").write_text(json.dumps({
                    "source_fingerprints": {
                        "source_file_sha256": bridge.SOURCE_SHA,
                        "loaded_m1_bidask_sha256": "f" * 64,
                    },
                    "trades_exposed_to_uncertain_gaps": 0,
                    "forced_end_of_data_closures": 0,
                }), encoding="utf-8")
            rows.append({
                "ordinal": ordinal, "identity": identity,
                "relative_dir": folder.name, "reference_fast_parity": "PASSED",
                "metrics": fake_metrics.copy(),
            })
        index = {
            "schema": bridge.INDEX_SCHEMA, "training_only": True,
            "independent_oos_proven": False, "live_trading_authorized": False,
            "data_archive_sha256": bridge.SOURCE_SHA,
            "training_input_sha256": dispatch["training_input_sha256"],
            "generation_manifest_sha256": dispatch["generation_manifest_sha256"],
            "year": year, "requested_start_ordinal": start_ordinal,
            "requested_limit": limit, "completed": len(rows),
            "all_in_cost_per_ounce": 0.40, "results": rows,
        }
        (destination / "training_replay_index.json").write_text(
            json.dumps(index), encoding="utf-8")
        calls.append((generation_manifest.parent.name, year, start_ordinal))

    monkeypatch.setattr(cycles, "replay", synthetic_replay)
    return source, archive, root, calls


def test_full_two_generation_wiring_with_real_feedback_and_restart(integrated):
    source, archive, root, calls = integrated
    first = cycles.run_cycles(
        source, archive, root, seed=17, first_generation=1,
        generations=2, proposal_count=2, shard_size=1)
    assert first["status"] == "COMPLETE_TRAINING_ONLY_NOT_OOS"
    assert [g["replay_shards"] for g in first["generations"]] == [4, 4]
    assert len(calls) == 8
    assert first["independent_oos_proven"] is False
    assert first["live_trading_authorized"] is False
    next_doc = json.loads((root / "generation_0002" /
                           "next_training_input.json").read_text())
    assert len(next_doc["candidates"]) == 5
    assert len(next_doc["explored_ids"]) == 5
    assert next_doc["years"] == [2012, 2013]
    for n in (1, 2):
        folder = root / f"generation_{n:04d}"
        evidence = json.loads(
            (folder / "next_training_input.json.evidence.json").read_text())
        assert evidence["complete_formula_year_pairs"] == 4
        assert evidence["independent_oos_proven"] is False
    replay_count = len(calls)
    again = cycles.run_cycles(
        source, archive, root, seed=17, first_generation=1,
        generations=2, proposal_count=2, shard_size=1)
    assert len(calls) == replay_count
    assert again == first


def test_missing_annual_evidence_blocks_next_generation(integrated, monkeypatch):
    source, archive, root, calls = integrated
    real_feedback = cycles.compile_feedback

    def reject_one_annual_shard(training_input, generation_manifest,
                                dispatch_dir, shards, output):
        # Simulate interrupted, incomplete annual coverage. The real
        # feedback bridge must reject it before emitting the next input.
        return real_feedback(training_input, generation_manifest,
                             dispatch_dir, shards[:-1], output)

    monkeypatch.setattr(cycles, "compile_feedback", reject_one_annual_shard)
    with pytest.raises(ValueError, match="missing training year"):
        cycles.run_cycles(source, archive, root, seed=17,
                          first_generation=1, generations=2,
                          proposal_count=2, shard_size=2)
    assert not (root / "generation_0001" / "next_training_input.json").exists()
    assert not (root / "generation_0002").exists()
