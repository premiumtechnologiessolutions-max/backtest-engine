"""Reconcile a COMPLETE arithmetic generation's exposed training replays into
the next immutable evolution input. No raw quotes, holdout, broker, or trading.

This is the missing feedback bridge between deterministic generation/dispatch
and the next generation. Every proposed formula must have a fully audited
reference/fast annual replay for EVERY frozen training year before ANY output.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from norisk_quant.research_evolution import _formula
from norisk_quant.research_training_integrity import training_summary
from norisk_quant.research_candidate_memory import select_training_memory
from scripts.materialize_arithmetic_generation import (
    _encoded, _load_strict, _publish_once, _verified_generation, materialize,
)
from scripts.run_arithmetic_dispatch_training import (
    REPORTS, SOURCE_SHA, _compare_outputs,
)

SCHEMA = "NRFX_ARITHMETIC_TRAINING_INPUT_V1"
EVIDENCE_SCHEMA = "NRFX_ARITHMETIC_FEEDBACK_EVIDENCE_V1"
INDEX_SCHEMA = "NRFX_ARITHMETIC_TRAINING_REPLAY_V1"
INDEX_FIELDS = {
    "schema", "training_only", "independent_oos_proven",
    "live_trading_authorized", "data_archive_sha256",
    "training_input_sha256", "generation_manifest_sha256", "year",
    "requested_start_ordinal", "requested_limit", "completed",
    "all_in_cost_per_ounce", "results",
}
ROW_FIELDS = {"ordinal", "identity", "reference_fast_parity", "metrics", "relative_dir"}


def _regular(path: Path) -> Path:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or symlinked frozen evidence: " + path.name)
    return path


def _directory(path: Path) -> Path:
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Missing or symlinked replay directory")
    return path


def _sha(path: Path) -> str:
    h = sha256()
    with _regular(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _checked_index(index: object, dispatch: dict, year_set: set[int],
                   input_sha: str) -> tuple[int, list[dict]]:
    if type(index) is not dict or set(index) != INDEX_FIELDS:
        raise ValueError("Noncanonical annual replay index schema")
    if (index["schema"] != INDEX_SCHEMA or index["training_only"] is not True
            or index["independent_oos_proven"] is not False
            or index["live_trading_authorized"] is not False
            or index["data_archive_sha256"] != SOURCE_SHA
            or index["training_input_sha256"] != input_sha
            or index["generation_manifest_sha256"] != dispatch["generation_manifest_sha256"]
            or type(index["year"]) is not int or index["year"] not in year_set
            or index["all_in_cost_per_ounce"] != 0.40
            or type(index["all_in_cost_per_ounce"]) not in (int, float)):
        raise ValueError("Replay index violates frozen training provenance")
    start, limit, completed, rows = (
        index["requested_start_ordinal"], index["requested_limit"],
        index["completed"], index["results"],
    )
    if (type(start) is not int or type(limit) is not int
            or type(completed) is not int or type(rows) is not list
            or start < 1 or not 1 <= limit <= 128
            or start > dispatch["formula_count"]):
        raise ValueError("Invalid frozen ordinal window")
    expected = list(range(start, min(dispatch["formula_count"], start + limit - 1) + 1))
    if completed != len(rows) or len(rows) != len(expected):
        raise ValueError("Incomplete annual replay shard")
    for row, ordinal in zip(rows, expected):
        if type(row) is not dict or set(row) != ROW_FIELDS:
            raise ValueError("Invalid annual replay result schema")
        formula = dispatch["formulas"][ordinal - 1]
        if (type(row["ordinal"]) is not int or row["ordinal"] != ordinal
                or row["identity"] != formula["identity"]
                or row["reference_fast_parity"] != "PASSED"
                or row["relative_dir"] != f"{ordinal:03d}_{formula['identity'][:16]}"
                or type(row["metrics"]) is not dict):
            raise ValueError("Replay shard identity, parity or ordinal mismatch")
    return index["year"], rows


def compile_feedback(training_input: Path, generation_manifest: Path,
                     dispatch_dir: Path, replay_dirs: list[Path],
                     output: Path) -> dict:
    """Reaudit every annual reference/fast report; publish only full coverage.

    Source paths are local/private. The published next-generation JSON contains
    only validated aggregate training evidence, never raw quotes or trade fills.
    """
    if type(replay_dirs) is not list or not 1 <= len(replay_dirs) <= 4096:
        raise ValueError("Explicit bounded annual replay shards required")
    _regular(training_input)
    _regular(generation_manifest)
    source, input_sha = _load_strict(training_input)
    generation, verified_sha = _verified_generation(training_input, generation_manifest)
    if verified_sha != input_sha or source.get("schema") != SCHEMA:
        raise ValueError("Frozen training input mismatch")
    years = tuple(source["years"])
    if (len(years) < 2 or any(type(y) is not int for y in years)
            or years != tuple(sorted(set(years)))):
        raise ValueError("At least two distinct chronological training years required")
    # Verify the original deterministic generation and every dispatch formula.
    dispatch = materialize(training_input, generation_manifest, dispatch_dir)
    if (dispatch["generation_manifest_sha256"] != generation["manifest_sha256"]
            or dispatch["training_years"] != list(years)):
        raise ValueError("Frozen dispatch does not match original generation")
    expected_ids = {r["identity"] for r in dispatch["formulas"]}
    records = {identity: {} for identity in expected_ids}
    fingerprints = {}
    provenance = []
    visited = set()
    for directory in sorted(map(_directory, replay_dirs), key=lambda p: str(p.resolve())):
        resolved = directory.resolve()
        if resolved in visited:
            raise ValueError("Duplicate replay directory")
        visited.add(resolved)
        index_path = _regular(directory / "training_replay_index.json")
        index, _ = _load_strict(index_path)
        year, rows = _checked_index(index, dispatch, set(years), input_sha)
        shard = {"year": year, "index_sha256": _sha(index_path),
                 "ordinals": [], "reports": []}
        for row in rows:
            ordinal, identity = row["ordinal"], row["identity"]
            if year in records[identity]:
                raise ValueError("Duplicate annual formula evidence")
            folder = _directory(directory / row["relative_dir"])
            left, right = (_directory(folder / name) for name in ("reference", "fast"))
            for root in (left, right):
                for filename in (*REPORTS, "summary.json"):
                    _regular(root / filename)
            # Reconstruct all ledgers and compare reference/fast anew; an
            # index with self-reported PASSED is not sufficient evidence.
            metrics = _compare_outputs(left, right, identity=identity, year=year)
            if row["metrics"] != metrics:
                raise ValueError("Persisted replay index metrics differ from audited reports")
            summary, _ = _load_strict(left / "summary.json")
            fingerprint = summary["source_fingerprints"]
            if fingerprint.get("source_file_sha256") != SOURCE_SHA:
                raise ValueError("Annual engine report used a different source archive")
            bidask = metrics["bidask_sha256"]
            if year in fingerprints and fingerprints[year] != bidask:
                raise ValueError("Same-year formula replays used different BID/ASK data")
            fingerprints[year] = bidask
            monthly = pd.read_csv(left / "monthly.csv")
            periods = [f"{year}-{month:02d}" for month in range(1, 13)]
            if monthly["period"].tolist() != periods:
                raise ValueError("Training year has incomplete monthly observations")
            annual = {
                "months": {period: float(net) for period, net in
                           zip(periods, monthly["net_pnl"])},
                "net_usd_per_oz": metrics["net_usd_per_oz"],
                "trades": metrics["trades"],
                "fees_usd": metrics["fees_usd"],
                "positive_months": metrics["positive_months"],
                "uncertain_gap_trades": summary["trades_exposed_to_uncertain_gaps"],
                "synthetic_forced_closures": summary["forced_end_of_data_closures"],
                "accounting": "PASSED",
            }
            records[identity][year] = annual
            shard["ordinals"].append(ordinal)
            shard["reports"].append({
                "identity": identity,
                "reference_summary_sha256": _sha(left / "summary.json"),
                "fast_summary_sha256": _sha(right / "summary.json"),
                "reference_trades_sha256": _sha(left / "trades.csv"),
                "fast_trades_sha256": _sha(right / "trades.csv"),
            })
        provenance.append(shard)
    if any(set(annual) != set(years) for annual in records.values()):
        raise ValueError("Generation has missing training year/formula replay coverage")
    next_candidates = list(source["candidates"])
    known = set()
    for candidate in next_candidates:
        identity = _formula(candidate["formula"]).identity()
        if identity in known:
            raise ValueError("Duplicate prior candidate identity")
        known.add(identity)
        training_summary(candidate["records"], years)
    for proposal in generation["proposals"]:
        identity = proposal["identity"]
        if identity in known:
            raise ValueError("Already evaluated proposal duplicates prior candidate")
        known.add(identity)
        candidate = {
            "formula": proposal["formula"],
            "records": [{"year": year, "metrics": records[identity][year]} for year in years],
        }
        training_summary(candidate["records"], years)
        next_candidates.append(candidate)
    # Scale across generations WITHOUT widening the active parent pool.
    # Every candidate is audited before selection and every rejected/evicted
    # identity remains in explored_ids to prevent rediscovery. Preserve the
    # legacy exact output for <=128 candidates and existing immutable replays.
    memory = None
    if len(next_candidates) > 128:
        memory = select_training_memory(next_candidates, years, limit=128)
        next_candidates = memory["active_candidates"]
    explored = sorted(set(source["explored_ids"]) | known)
    if len(explored) > 100_000:
        raise ValueError("Exploration history exceeds bounded evolution limit")
    next_input = {"schema": SCHEMA, "years": list(years),
                  "candidates": next_candidates, "explored_ids": explored}
    output = Path(output)
    evidence_path = output.with_name(output.name + ".evidence.json")
    if (output.resolve() in {Path(training_input).resolve(),
                            Path(generation_manifest).resolve()}
            or evidence_path.resolve() in {Path(training_input).resolve(),
                                           Path(generation_manifest).resolve()}
            or any(output.resolve().is_relative_to(path) or
                   evidence_path.resolve().is_relative_to(path)
                   for path in visited)):
        raise ValueError("Feedback output cannot replace frozen input or replay evidence")
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "training_only": True,
        "independent_oos_proven": False,
        "live_trading_authorized": False,
        "original_archive_sha256": SOURCE_SHA,
        "training_input_sha256": input_sha,
        "generation_manifest_sha256": generation["manifest_sha256"],
        "training_years": list(years),
        "evaluated_formulas": len(records),
        "complete_formula_year_pairs": len(years) * len(records),
        "next_input_sha256": sha256(_encoded(next_input)).hexdigest(),
        "replay_shards": provenance,
    }
    if memory is not None:
        # Compact, audit-friendly selection decisions; NO raw market data.
        evidence["active_memory_selection"] = {
            "method": memory["selection_method"],
            "universe_size": memory["universe_size"],
            "active_size": memory["active_size"],
            "evicted_count": memory["evicted_count"],
            "evicted": memory["evicted"],
            "independent_oos_proven": False,
        }
    if any(p.is_symlink() for p in (output, evidence_path, *output.parents)):
        raise ValueError("Symlinked feedback output path is forbidden")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish evidence first. An interrupted run cannot expose a standalone
    # next-generation input without its evidence sidecar.
    _publish_once(evidence_path, _encoded(evidence))
    _publish_once(output, _encoded(next_input))
    return {"status": "COMPLETE_EXPOSED_TRAINING_FEEDBACK_NOT_OOS",
            "evaluated_formulas": len(records), "training_years": list(years),
            "next_candidate_count": len(next_candidates),
            "next_input_sha256": evidence["next_input_sha256"],
            "evidence_path": str(evidence_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-input", type=Path, required=True)
    parser.add_argument("--generation-manifest", type=Path, required=True)
    parser.add_argument("--dispatch-dir", type=Path, required=True)
    parser.add_argument("--replay-dir", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(compile_feedback(
        args.training_input, args.generation_manifest, args.dispatch_dir,
        args.replay_dir, args.out), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
