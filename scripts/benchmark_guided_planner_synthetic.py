"""Synthetic-only planning capacity benchmark: NEVER market backtests or OOS.

No quotes, private trades, external calls, trading orders or PnL evidence.
Only frozen training candidates may initialize deterministic planning.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import time

from norisk_quant.research_evolution import evolve_training_generation, _formula
from norisk_quant.research_candidate_memory import select_training_memory
from scripts.materialize_arithmetic_generation import _load_strict


def benchmark(source_path: Path, *, generations: int = 100,
              per_generation: int = 10) -> dict:
    if (type(generations) is not int or type(per_generation) is not int
            or not 1 <= generations <= 200 or not 1 <= per_generation <= 32
            or generations * per_generation > 5000):
        raise ValueError("Bounded synthetic planner budget exceeded")
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError("Frozen training input must be a regular file")
    source, _ = _load_strict(source_path)
    if (type(source) is not dict or set(source) !=
            {"schema", "years", "candidates", "explored_ids"}
            or source["schema"] != "NRFX_ARITHMETIC_TRAINING_INPUT_V1"):
        raise ValueError("Unexpected frozen training input")

    years = tuple(source["years"])
    active = source["candidates"]
    explored = set(source["explored_ids"])
    select_training_memory(active, years)
    explored.update(_formula(c["formula"]).identity() for c in active)
    started = time.perf_counter()
    count = guided = 0
    for gen in range(1, generations + 1):
        manifest = evolve_training_generation(
            active, years, seed=31 + gen, generation=gen,
            proposal_count=per_generation,
            explored_ids=tuple(sorted(explored)),
            proposal_policy="matched_guided_v1")
        guided += manifest["planning_diagnostics"]["guided_proposals"]
        new = []
        for proposal in manifest["proposals"]:
            identity = proposal["identity"]
            records = []
            for y in years:
                # Fabricated fixture strictly for throughput tests.
                # These numbers are NOT simulated or historical market returns.
                values = [
                    (int(sha256(f"{identity}:{y}-{m}".encode()).hexdigest()[:4], 16)
                     % 201 - 100) / 100.
                    for m in range(1, 13)
                ]
                records.append({"year": y, "metrics": {
                    "months": {f"{y}-{m:02d}": v
                               for m, v in enumerate(values, 1)},
                    "net_usd_per_oz": round(sum(values), 8),
                    "trades": 12, "fees_usd": 4.8,
                    "positive_months": sum(v > 0 for v in values),
                    "uncertain_gap_trades": 0,
                    "synthetic_forced_closures": 0,
                    "accounting": "PASSED",
                }})
            new.append({"formula": proposal["formula"], "records": records})
            explored.add(identity)
        count += len(new)
        memory = select_training_memory(active + new, years)
        active = memory["active_candidates"]
    return {
        "proof_type": "SYNTHETIC_GENERATION_ONLY_NO_BACKTEST",
        "generations": generations, "new_unique_formulas": count,
        "guided_proposals": guided, "active_parents": len(active),
        "total_explored_identities": len(explored),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "independent_oos_proven": False,
        "live_trading_authorized": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--generations", type=int, default=100)
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args(argv)
    print(json.dumps(benchmark(args.input, generations=args.generations,
                               per_generation=args.count), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
