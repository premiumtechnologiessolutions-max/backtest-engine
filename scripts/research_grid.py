"""Pre-register bounded, deterministic parameter grids as explicit batch plans.

Generates up to 20,000 candidates across <=50-spec shards, without reading
market prices, tuning on historical results, running backtests or trading.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import itertools
import json
from pathlib import Path
import re

try:
    from scripts.research_batch import (
        MAX_EXPERIMENTS, PARAMS, ResearchBatchError, validate_plan,
    )
except ModuleNotFoundError:
    from research_batch import MAX_EXPERIMENTS, PARAMS, ResearchBatchError, validate_plan

GRID_SCHEMA = "NRFX_GRID_V1"
MAX_GRID_CANDIDATES = 20000
PREFIX = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,45}\Z")


def expand_grid(grid: object) -> tuple[list[dict], dict]:
    if not isinstance(grid, dict) or set(grid) != {
        "schema", "source", "source_sha256", "engine_commit", "start", "end", "grids"
    } or grid["schema"] != GRID_SCHEMA:
        raise ResearchBatchError("Grid requires exact NRFX_GRID_V1 schema")
    groups = grid["grids"]
    if not isinstance(groups, list) or not 1 <= len(groups) <= 100:
        raise ResearchBatchError("Grid requires 1..100 families")
    base = {key: grid[key] for key in (
        "source", "source_sha256", "engine_commit", "start", "end"
    )}
    base["schema"] = "NRFX_BATCH_V1"
    accepted, rejected = [], []
    total_raw = 0
    prefixes, signatures = set(), set()
    for group in groups:
        if not isinstance(group, dict) or set(group) != {
            "id_prefix", "strategy", "timeframe", "execution", "axes"
        }:
            raise ResearchBatchError("Grid family must declare exact fields")
        prefix, strategy = group["id_prefix"], group["strategy"]
        if not isinstance(prefix, str) or not PREFIX.fullmatch(prefix) or prefix in prefixes:
            raise ResearchBatchError("Grid prefixes must be safe and unique")
        prefixes.add(prefix)
        if strategy not in PARAMS:
            raise ResearchBatchError("Unknown grid strategy")
        axes = group["axes"]
        if not isinstance(axes, dict) or set(axes) != set(PARAMS[strategy]):
            raise ResearchBatchError("Grid axes must explicitly cover every parameter")
        keys = sorted(axes)
        values = []
        for key in keys:
            axis = axes[key]
            if not isinstance(axis, list) or not 1 <= len(axis) <= 100:
                raise ResearchBatchError("Each parameter axis needs 1..100 values")
            try:
                serialized = [json.dumps(value, sort_keys=True, allow_nan=False)
                              for value in axis]
            except (TypeError, ValueError) as exc:
                raise ResearchBatchError("Non-finite/non-JSON grid axis") from exc
            if len(serialized) != len(set(serialized)):
                raise ResearchBatchError("Duplicate axis values inflate independent tests")
            values.append(axis)
        candidates = 1
        for axis in values:
            candidates *= len(axis)
        if candidates + total_raw > MAX_GRID_CANDIDATES:
            raise ResearchBatchError(f"Grid would exceed {MAX_GRID_CANDIDATES} candidates")
        total_raw += candidates
        for i, combo in enumerate(itertools.product(*values), start=1):
            parameters = dict(zip(keys, combo))
            spec = {
                "id": f"{prefix}_{i:05d}", "strategy": strategy,
                "timeframe": group["timeframe"], "execution": group["execution"],
                "parameters": parameters,
            }
            try:
                validate_plan({**base, "experiments": [spec]})
            except ResearchBatchError as exc:
                if strategy == "ema" and str(exc) == "EMA fast must be strictly less than slow":
                    rejected.append({"id": spec["id"], "reason": "EMA_FAST_GE_SLOW"})
                    continue
                raise
            signature = json.dumps({
                "strategy": strategy, "timeframe": group["timeframe"],
                "execution": group["execution"], "parameters": parameters,
            }, sort_keys=True, allow_nan=False)
            if signature in signatures:
                raise ResearchBatchError("Duplicate configuration across grid families")
            signatures.add(signature)
            accepted.append(spec)
    if not accepted:
        raise ResearchBatchError("No valid parameter specifications remain")
    return accepted, {
        "raw_combinations": total_raw, "accepted": len(accepted),
        "rejected": len(rejected), "rejected_specs": rejected,
    }


def write_shards(grid: dict, out: Path) -> dict:
    specs, audit = expand_grid(grid)
    if out.exists():
        raise ResearchBatchError("Grid destination already exists; refuse overwrite")
    out.mkdir(parents=True)
    frozen = {k: grid[k] for k in (
        "source", "source_sha256", "engine_commit", "start", "end"
    )}
    frozen["schema"] = "NRFX_BATCH_V1"
    parts = []
    for offset in range(0, len(specs), MAX_EXPERIMENTS):
        plan = {**frozen, "experiments": specs[offset:offset + MAX_EXPERIMENTS]}
        validate_plan(plan)
        content = json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        name = f"batch_{offset // MAX_EXPERIMENTS + 1:05d}.json"
        (out / name).write_text(content, encoding="utf-8")
        parts.append({
            "file": name, "sha256": sha256(content.encode("utf-8")).hexdigest(),
            "experiments": len(plan["experiments"]),
        })
    manifest = {
        "schema": "NRFX_GRID_EXPANDED_V1",
        "status": "FROZEN_PLANS_ONLY_NO_BACKTEST_EXECUTED",
        "research_status": "HISTORICALLY_EXPOSED_NOT_OOS",
        "source_sha256": grid["source_sha256"],
        "engine_commit": grid["engine_commit"],
        "grid_stats": audit, "shards": parts,
    }
    (out / "grid_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    result = write_shards(json.loads(args.grid.read_text(encoding="utf-8")), args.out)
    print(json.dumps({
        "status": result["status"], "shards": len(result["shards"]),
        "generated": result["grid_stats"]["accepted"],
        "rejected": result["grid_stats"]["rejected"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
