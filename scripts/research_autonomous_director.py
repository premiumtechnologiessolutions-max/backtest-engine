"""Self-driving, bounded, RESUMABLE research director for private XAUUSD training.

After a single invocation, advances the existing canonical generator -> both
execution engines -> independent accounting -> feedback -> next generation
pipeline. It DOES NOT search holdout data, access brokers or trade live.

The pinned original Gold ZIP must already be accessible to the running host.
A GitHub CI runner with no private market data cannot execute this campaign.
Research continues only while this process is running; restart with the same
arguments to verify/resume the immutable campaign. Output is never in Git.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time

from scripts.bootstrap_arithmetic_training import _validate_years
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA, _digest
from scripts.run_quant_research_platform import run_pipeline, _safe_private_root
from scripts.research_batch_orchestrator import exclusive_batch_lock

SCHEMA = "NRFX_AUTONOMOUS_TRAINING_DIRECTOR_V1"
POLICY = "matched_guided_v1"


def _persist(root: Path, state: dict) -> None:
    """Atomic, private checkpoint. Never store raw quotes or source paths."""
    dest = root / "autonomous_research_status.json"
    if dest.is_symlink():
        raise ValueError("Autonomous status symlink refused")
    payload = (json.dumps(state, sort_keys=True, indent=2, allow_nan=False)
               + "\n").encode("utf-8")
    fd, staged = tempfile.mkstemp(prefix=".autonomous-status-", dir=root)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if dest.is_symlink():
            raise ValueError("Autonomous status symlink refused")
        os.replace(staged, dest)
    finally:
        Path(staged).unlink(missing_ok=True)



def _completed_hint(root: Path) -> int:
    """Choose a resume ceiling; this is NOT evidence verification.

    The canonical campaign must independently re-attest every cached replay.
    Do not start a restarted director at generation one when later immutable
    generations already exist (the dashboard includes all cached generations).
    """
    cycles = root / "campaign" / "cycles"
    if not cycles.exists():
        return 0
    if cycles.is_symlink() or not cycles.is_dir():
        raise ValueError("Unsafe existing campaign cycles")
    count = 0
    for ordinal in range(1, 201):
        folder = cycles / f"generation_{ordinal:04d}"
        if folder.is_symlink():
            raise ValueError("Symlinked campaign generation")
        if not folder.is_dir():
            break
        feedback = folder / "next_training_input.json"
        if feedback.is_symlink():
            raise ValueError("Symlinked campaign feedback")
        if not feedback.is_file():
            break
        count += 1
    return count


def drive(gold_zip: Path, root: Path, *, years: list[int], seed: int,
          target_generations: int = 60, step_generations: int = 5,
          proposal_count: int = 12, shard_size: int = 8,
          min_free_gb: int = 2, max_batch_wall_seconds: int = 7200,
          max_total_wall_seconds: int = 86400,
          max_resume_attempts: int = 100) -> dict:
    """Keep advancing immutable verified training generations without prompts.

    A failed audit is never retried as a success. Time/disk pauses are durable.
    Wall-time controls are checkpoints BETWEEN generations, not kill switches
    for an in-flight source backtest. Existing complete generations are
    re-attested by the platform on every attempt; never trusted by directory
    names or this director's state file.
    """
    _validate_years(years)
    values = (seed, target_generations, step_generations, proposal_count,
              shard_size, min_free_gb, max_batch_wall_seconds,
              max_total_wall_seconds, max_resume_attempts)
    if (any(type(v) is not int for v in values)
            or not 0 <= seed < 2**63
            or not 1 <= target_generations <= 200
            or not 1 <= step_generations <= 200
            or not 1 <= proposal_count <= 128
            or not 1 <= shard_size <= 128
            or not 0 <= min_free_gb <= 128
            or not 60 <= max_batch_wall_seconds <= 86400
            or not 60 <= max_total_wall_seconds <= 604800
            or not 1 <= max_resume_attempts <= 1000):
        raise ValueError("Invalid bounded autonomous research controls")
    gold_zip, root = Path(gold_zip), Path(root)
    if (gold_zip.is_symlink() or not gold_zip.is_file()
            or gold_zip.suffix.lower() != ".zip"
            or _digest(gold_zip) != SOURCE_SHA):
        raise ValueError("Authorized SHA-pinned original Gold ZIP unavailable")
    if gold_zip.resolve().is_relative_to(root.resolve()):
        raise ValueError("Gold ZIP cannot be inside research output")
    _safe_private_root(root)
    gold_zip, root = gold_zip.resolve(strict=True), root.resolve()
    resumed_hint = _completed_hint(root)
    if resumed_hint > target_generations:
        raise ValueError("Target smaller than existing immutable campaign")
    started = time.monotonic()
    state = {
        "schema": SCHEMA, "status": "RUNNING_TRAINING_ONLY_NOT_OOS",
        "proposal_policy": POLICY, "source_sha256": SOURCE_SHA,
        "training_years": list(years), "target_generations": target_generations,
        "verified_generations": 0, "attempts": 0,
        "new_formulas_requested_per_generation": proposal_count,
        "training_only": True, "historical_exposed": True,
        "independent_oos_proven": False, "market_edge_confirmed": False,
        "live_trading_authorized": False,
        "updated_utc": datetime.now(timezone.utc).isoformat(),
    }
    # Separate director lock; nested platform locks use a different directory.
    control = root / ".director_control"
    if control.is_symlink() or (control.exists() and not control.is_dir()):
        raise ValueError("Unsafe director lock directory")
    control.mkdir(mode=0o700, exist_ok=True)
    with exclusive_batch_lock(control):
        _persist(root, state)
        # The hint only selects how far to request; no cached result is
        # trusted until run_pipeline independently reaudits it.
        next_ceiling = ((resumed_hint // step_generations) + 1) * step_generations
        target = min(target_generations, max(step_generations, next_ceiling))
        last_verified = 0
        try:
            for attempt in range(1, max_resume_attempts + 1):
                if time.monotonic() - started >= max_total_wall_seconds:
                    state["status"] = "PAUSED_TOTAL_TIME_BUDGET"
                    break
                outcome = run_pipeline(
                    gold_zip, root, years=years, seed=seed,
                    generations=target, proposal_count=proposal_count,
                    shard_size=shard_size, min_free_gb=min_free_gb,
                    max_wall_seconds=max_batch_wall_seconds,
                    proposal_policy=POLICY)
                if type(outcome) is not dict or type(outcome.get("campaign")) is not dict:
                    raise ValueError("Platform omitted audited campaign")
                campaign = outcome["campaign"]
                completed = campaign.get("completed")
                if (type(completed) is not list
                        or not last_verified <= len(completed) <= target
                        or any(type(x) is not dict or type(x.get("generation")) is not int
                               or x["generation"] != i + 1
                               for i, x in enumerate(completed))):
                    raise ValueError("Non-monotone or unverified generation lineage")
                count = len(completed)
                dashboard = outcome.get("dashboard")
                if count and (type(dashboard) is not dict
                              or dashboard.get("verified_generations") != count):
                    raise ValueError("Director refuses unaudited dashboard")
                state["attempts"] = attempt
                state["verified_generations"] = count
                state["requested_generation_ceiling"] = target
                state["last_platform_status"] = outcome["status"]
                state["updated_utc"] = datetime.now(timezone.utc).isoformat()
                if outcome["status"] == "COMPLETE_EXPOSED_TRAINING_PIPELINE_NOT_OOS":
                    if count != target:
                        raise ValueError("Platform claimed incomplete target as complete")
                    if count == target_generations:
                        state["status"] = "COMPLETE_HISTORICAL_TRAINING_ONLY_NOT_OOS"
                        break
                    target = min(target_generations, target + step_generations)
                    last_verified = count
                    _persist(root, state)
                    continue
                if outcome["status"] != "PAUSED_EXPOSED_TRAINING_PIPELINE_NOT_OOS":
                    raise ValueError("Unexpected platform status")
                reason = campaign.get("status")
                if reason == "PAUSED_DISK_BUDGET":
                    state["status"] = "PAUSED_DISK_BUDGET"
                    break
                if reason != "PAUSED_TIME_BUDGET_BETWEEN_GENERATIONS":
                    raise ValueError("Unknown campaign pause reason")
                if count <= last_verified:
                    state["status"] = "PAUSED_NO_GENERATION_PROGRESS"
                    break
                last_verified = count
                _persist(root, state)
            else:
                state["status"] = "PAUSED_RESUME_ATTEMPTS_BUDGET"
        except Exception:
            state["status"] = "FAILED_REQUIRES_EVIDENCE_REVIEW"
            state["updated_utc"] = datetime.now(timezone.utc).isoformat()
            _persist(root, state)
            raise
        state["updated_utc"] = datetime.now(timezone.utc).isoformat()
        _persist(root, state)
        return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--years", nargs="+", type=int, default=[2012, 2013])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--target-generations", type=int, default=60)
    parser.add_argument("--step-generations", type=int, default=5)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--shard-size", type=int, default=8)
    parser.add_argument("--min-free-gb", type=int, default=2)
    parser.add_argument("--max-batch-wall-seconds", type=int, default=7200)
    parser.add_argument("--max-total-wall-seconds", type=int, default=86400)
    parser.add_argument("--max-resume-attempts", type=int, default=100)
    args = parser.parse_args(argv)
    report = drive(args.gold_zip, args.out, years=args.years, seed=args.seed,
                   target_generations=args.target_generations,
                   step_generations=args.step_generations,
                   proposal_count=args.count, shard_size=args.shard_size,
                   min_free_gb=args.min_free_gb,
                   max_batch_wall_seconds=args.max_batch_wall_seconds,
                   max_total_wall_seconds=args.max_total_wall_seconds,
                   max_resume_attempts=args.max_resume_attempts)
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0 if report["status"].startswith("COMPLETE_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
