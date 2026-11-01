"""Scale-only frozen strategy planning probe; no market data or backtests.

Validates the number, uniqueness and deterministic identity of up to 50,000
research specifications. This is NOT evidence of 50,000 executed backtests,
broker performance, prospective OOS or runtime resource capacity.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import time
import tracemalloc

from scripts.research_batch_orchestrator import SCHEMA, expand, run_plan

SOURCE = "a" * 64  # synthetic sentinel, not a Gold archive fingerprint
COMMIT = "b" * 40  # synthetic sentinel, not an audited Git SHA


def frozen_plan(count: int) -> dict:
    if type(count) is not int or not 100 <= count <= 50000 or count % 100:
        raise ValueError("Scale jobs must be a multiple of 100, from 100 to 50000")
    return {
        "schema": SCHEMA,
        "dataset": "/NONEXISTENT_ORIGINAL_GOLD_ARCHIVE_FOR_PLANNING_ONLY.zip",
        "source_sha256": SOURCE,
        "engine_commit": COMMIT,
        "exposure_context": "historical_exposed",
        "jobs": [],
        "grids": [{
            "id_prefix": "scale",
            "strategy": "ema",
            "timeframe": "M1",
            "execution": "fast",
            "start": "2012-01-01",
            "end": "2012-12-31",
            "grid": {
                "fast": list(range(2, 102)),
                "slow": list(range(102, 102 + count // 100)),
            },
        }],
    }


def benchmark(count: int = 20000, *, max_jobs_per_invocation: int = 500) -> dict:
    if (type(max_jobs_per_invocation) is not int
            or not 1 <= max_jobs_per_invocation <= 500):
        raise ValueError("Max job budget must be an integer 1..500")
    plan = frozen_plan(count)
    before = time.perf_counter()
    tracemalloc.start()
    try:
        jobs, fingerprint = expand(plan)
        _current, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    seconds = time.perf_counter() - before
    if len(jobs) != count:
        raise AssertionError("Frozen plan expansion lost specifications")
    ids = {job["id"] for job in jobs}
    if len(ids) != count:
        raise AssertionError("Frozen plan expansion reused job IDs")
    unique_specs = {
        sha256(json.dumps(job["spec"], sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        for job in jobs
    }
    if len(unique_specs) != count:
        raise AssertionError("Frozen plan expansion contains duplicate strategy specs")
    receipt = run_plan(plan, Path("/NONEXISTENT_NO_OUTPUT"),
                       max_jobs=max_jobs_per_invocation, dry_run=True)
    if receipt != {
        "status": "DEFINED_ONLY_NO_BACKTEST",
        "jobs": count,
        "plan_sha256": fingerprint,
        "budget": max_jobs_per_invocation,
    }:
        raise AssertionError("Dry-run planned an unexpected execution scope")
    return {
        "schema": "NRFX_RESEARCH_SCALE_PLANNING_PROBE_V1",
        "status": "SPECIFICATIONS_EXPANDED_NO_MARKET_EXECUTION",
        "jobs_defined": count,
        "unique_job_ids": len(ids),
        "unique_strategy_specs": len(unique_specs),
        "job_budget_per_invocation": max_jobs_per_invocation,
        "invocations_needed_if_all_executed": math.ceil(count / max_jobs_per_invocation),
        "plan_sha256": fingerprint,
        "seconds_for_expansion_only": round(seconds, 3),
        "peak_python_tracemalloc_mib_expansion_only": round(peak_bytes / (1024 * 1024), 3),
        "data_source_opened": False,
        "market_backtests_executed": 0,
        "resource_usage_for_market_backtests_measured": False,
        "independent_oos_proven": False,
        "live_trading_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=20000)
    parser.add_argument("--max-jobs-per-invocation", type=int, default=500)
    args = parser.parse_args(argv)
    print(json.dumps(benchmark(
        args.jobs, max_jobs_per_invocation=args.max_jobs_per_invocation),
        indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
