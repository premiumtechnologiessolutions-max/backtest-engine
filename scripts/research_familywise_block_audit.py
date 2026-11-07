"""Training-only paired circular-block max-statistic sensitivity audit.

This is an exploratory *historically exposed* diagnostic, not an OOS test,
not a live-trading approval and not a guarantee of calibrated p-values.
Every candidate in a frozen, complete research batch is included, including
losing candidates. Identical sampled month indices preserve cross-candidate
calendar dependence. The bootstrap is mean-centered under a common null.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

try:
    from scripts import research_batch_orchestrator as batch
    from scripts.research_candidate_screen import months_between
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    import research_batch_orchestrator as batch
    from research_candidate_screen import months_between

SCHEMA = "NRFX_HISTORICAL_FAMILYWISE_BLOCK_AUDIT_V1"


def paired_block_max_test(matrix: np.ndarray, job_ids: list[str], *,
                          block_length: int, replicates: int = 1999,
                          seed: int = 20261030) -> dict:
    """Estimate the maximum *mean monthly net* null using paired block draws.

    Rows are consecutive calendar months; columns are *all* predeclared
    candidate variants. Circular blocks are sampled with replacement.
    The centered bootstrap is only an exploratory dependence sensitivity:
    a short/nonstationary series or data-mined universe invalidates claims
    of formal significance or future profitability.
    """
    x = np.asarray(matrix)
    if (x.ndim != 2 or x.dtype.kind not in "fi" or x.shape[0] < 12
            or x.shape[1] < 1 or x.shape[1] > 50000
            or not np.isfinite(x).all()):
        raise ValueError("Require finite numeric [>=12 months, 1..50000 candidates] matrix")
    months, candidates = x.shape
    if (type(job_ids) is not list or len(job_ids) != candidates
            or any(type(j) is not str or not j for j in job_ids)
            or len(set(job_ids)) != candidates):
        raise ValueError("Candidate IDs must be unique and complete")
    if type(block_length) is not int or not 1 <= block_length <= months // 3:
        raise ValueError("Invalid circular block length: require at least three sampled blocks")
    if type(replicates) is not int or not 999 <= replicates <= 20000:
        raise ValueError("Replicates must be an integer between 999 and 20000")
    if type(seed) is not int or not 0 <= seed < 2**63:
        raise ValueError("Seed must be a nonnegative 63-bit integer")
    # Cast once, not on every draw; means computed from the exact supplied
    # candidate/month universe. No review-period values are accepted here.
    x = x.astype(np.float64, copy=False)
    means = x.mean(axis=0)
    if not np.isfinite(means).all():
        raise ValueError("Monthly means overflowed")
    centered = x - means
    if not np.isfinite(centered).all():
        raise ValueError("Centered observations overflowed")
    best = int(np.argmax(means))  # deterministic tie break by sorted job ID
    observed_max = float(means[best])
    rng = np.random.default_rng(seed)
    # Sample the SAME calendar indices for all strategies. For efficiency,
    # aggregate resampled month multiplicities and matrix-multiply in chunks.
    # This preserves all candidates in the max: no winner-only resampling.
    exceed = 0
    null_maxima: list[float] = []
    nblocks = math.ceil(months / block_length)
    for start in range(0, replicates, 64):
        n = min(64, replicates - start)
        starts = rng.integers(0, months, size=(n, nblocks), dtype=np.int64)
        offsets = np.arange(block_length, dtype=np.int64)
        indices = ((starts[:, :, None] + offsets) % months).reshape(n, -1)[:, :months]
        weights = np.zeros((n, months), dtype=np.float64)
        for i in range(n):
            weights[i] = np.bincount(indices[i], minlength=months) / months
        maxes = np.max(weights @ centered, axis=1)
        if not np.isfinite(maxes).all():
            raise ValueError("Bootstrap null distribution overflowed")
        null_maxima.extend(float(v) for v in maxes)
        exceed += int(np.count_nonzero(maxes >= observed_max))
    # Plus-one avoids claiming zero probability from finite Monte Carlo.
    p_value = (exceed + 1) / (replicates + 1)
    return {
        "schema": SCHEMA,
        "method": "PAIRED_CIRCULAR_BLOCK_CENTERED_MAX_MONTHLY_MEAN_EXPLORATORY",
        "evidence_context": "HISTORICAL_EXPOSED_TRAINING_ONLY_NOT_OOS_NOT_LIVE_APPROVED",
        "calendar_months": months,
        "candidate_family_size": candidates,
        "best_job_id": job_ids[best],
        "best_mean_monthly_net_usd_per_oz": observed_max,
        "best_total_training_net_usd_per_oz": float(x[:, best].sum()),
        "best_positive_training_months": int(np.count_nonzero(x[:, best] > 0)),
        "bootstrap": {
            "replicates": replicates,
            "block_length_months": block_length,
            "seed": seed,
            "exceedances": exceed,
            "max_statistic_tail_fraction_exploratory": p_value,
            "null_max_mean_monthly_95pct_usd_per_oz": float(np.quantile(null_maxima, 0.95)),
        },
        "limitations": (
            "Exploratory historically exposed data; dependence/nonstationarity and "
            "selection of strategy families invalidate calibrated significance claims. "
            "No untouched OOS, no tick/broker validation, no live approval. "
            "A small tail fraction is NOT proof of a market edge."
        ),
    }


def audit(plan_path: Path, batch_output: Path, *, train_start: str,
          train_end: str, block_length: int = 3,
          replicates: int = 1999, seed: int = 20261030) -> dict:
    months = months_between(train_start, train_end)
    if len(months) < 12:
        raise ValueError("At least 12 consecutive training months required")
    plan = batch.read_strict_json(plan_path)
    jobs, plan_sha = batch.expand(plan)
    dataset = Path(plan["dataset"]).resolve(strict=True)
    if not dataset.is_file() or batch.file_sha(dataset) != plan["source_sha256"]:
        raise ValueError("Frozen private source SHA256 mismatch")
    if batch.checkout_commit() != plan["engine_commit"]:
        raise ValueError("Current checkout differs from frozen engine commit")
    if batch_output.is_symlink() or not batch_output.is_dir():
        raise ValueError("Missing or unsafe batch output directory")
    with batch.exclusive_batch_lock(batch_output):
        manifest = batch.read_strict_json(batch_output / "batch_manifest.json")
        if (type(manifest) is not dict
                or set(manifest) != {"schema", "plan_sha256", "source_sha256",
                                        "engine_commit", "results"}
                or manifest["schema"] != batch.SCHEMA
                or manifest["plan_sha256"] != plan_sha
                or manifest["source_sha256"] != plan["source_sha256"]
                or manifest["engine_commit"] != plan["engine_commit"]
                or type(manifest["results"]) is not dict):
            raise ValueError("Frozen batch manifest mismatch")
        defined = {job["id"]: job["spec"] for job in jobs}
        if set(manifest["results"]) != set(defined):
            raise ValueError("Incomplete or unknown candidate family; no max-statistic audit")
        # A common calendar is mandatory; never select only winning jobs.
        values = []
        for ident in sorted(defined):
            record = manifest["results"][ident]
            if type(record) is not dict or record.get("status") != batch.PASSED:
                raise ValueError("Candidate run is not fully reconciled")
            folder = batch_output / "runs" / ident
            if folder.is_symlink():
                raise ValueError("Unsafe candidate run directory")
            actual = batch.audit_run(folder, defined[ident],
                                     plan["source_sha256"], plan["engine_commit"])
            if actual != record:
                raise ValueError("Candidate evidence differs from frozen manifest")
            pnl = actual["monthly_net_pnl"]
            if not set(months).issubset(pnl):
                raise ValueError("Missing common training month in candidate")
            values.append([pnl[month] for month in months])
        if batch.file_sha(dataset) != plan["source_sha256"]:
            raise ValueError("Private source archive changed during familywise audit")
        result = paired_block_max_test(np.asarray(values, dtype=np.float64).T,
                                       sorted(defined), block_length=block_length,
                                       replicates=replicates, seed=seed)
        result.update({"plan_sha256": plan_sha,
                       "source_sha256": plan["source_sha256"],
                       "engine_commit": plan["engine_commit"],
                       "train_start": months[0], "train_end": months[-1],
                       "candidate_job_ids": sorted(defined)})
        # Atomic private output; no raw market data or candidate ledgers published.
        batch.atomic_manifest(batch_output / "familywise_block_audit.json", result)
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--batch-output", type=Path, required=True)
    parser.add_argument("--train-start", required=True)
    parser.add_argument("--train-end", required=True)
    parser.add_argument("--block-length", type=int, default=3)
    parser.add_argument("--replicates", type=int, default=1999)
    parser.add_argument("--seed", type=int, default=20261030)
    args = parser.parse_args(argv)
    result = audit(args.plan, args.batch_output,
                   train_start=args.train_start, train_end=args.train_end,
                   block_length=args.block_length,
                   replicates=args.replicates, seed=args.seed)
    print(json.dumps({"status": result["evidence_context"],
                      "candidate_family_size": result["candidate_family_size"],
                      "best_job_id": result["best_job_id"],
                      "exploratory_tail_fraction": result["bootstrap"]["max_statistic_tail_fraction_exploratory"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
