"""Offline one-command XAUUSD research platform: source -> seed -> research -> UI.

Never uploads original Gold data, calls brokers, places orders or certifies edge.
Every generated formula is retrospective TRAINING until separately preregistered
and tested on untouched forward observations. The campaign is bounded and
resumable; it does not run when the invoking process is stopped.

Example:
 python -m scripts.run_quant_research_platform \
   --gold-zip '/private/Gold data.zip' --out '/private/quant_platform' \
   --years 2012 2013 --seed 20261101 --generations 10 --count 12
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import tempfile

from scripts.bootstrap_arithmetic_training import bootstrap, _validate_years
from scripts.research_campaign_supervisor import campaign
from scripts.research_training_dashboard import build_dashboard
from scripts.research_batch_orchestrator import exclusive_batch_lock
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA, _digest
from scripts.run_arithmetic_research_cycles import _outside_checkout

SCHEMA = "NRFX_LOCAL_TRAINING_PLATFORM_V1"


def _status(root: Path, obj: dict) -> None:
    destination = root / "platform_status.json"
    if destination.is_symlink():
        raise ValueError("Symlinked platform status destination")
    payload = (json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    fd, staged = tempfile.mkstemp(prefix=".platform_status-", dir=root)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if destination.is_symlink():
            raise ValueError("Symlinked platform status destination")
        os.replace(staged, destination)
    finally:
        Path(staged).unlink(missing_ok=True)


def _safe_private_root(root: Path) -> None:
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("Research platform root/ancestor must not be symlinked")
    if root.exists() and not root.is_dir():
        raise ValueError("Research platform root must be a directory")
    _outside_checkout(root.resolve())
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        info = root.stat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise ValueError("Private research root must be owner-only (0700)")


def run_pipeline(gold_zip: Path, root: Path, *, years: list[int], seed: int,
                 generations: int = 10, proposal_count: int = 12,
                 shard_size: int = 8, min_free_gb: int = 2,
                 max_wall_seconds: int = 7200,
                 proposal_policy: str = "legacy_random") -> dict:
    """Execute real-source training and its UI with immutable resume/audits.

    The wall-time budget applies *between generations* of the campaign, not
    to the initial two-year source replay or a single in-progress generation.
    """
    _validate_years(years)
    controls = (seed, generations, proposal_count, shard_size,
                min_free_gb, max_wall_seconds)
    if (any(type(x) is not int for x in controls) or seed < 0
            or not 1 <= generations <= 200
            or not 1 <= proposal_count <= 128
            or not 1 <= shard_size <= 128
            or not 0 <= min_free_gb <= 1024
            or not 60 <= max_wall_seconds <= 86400
            or proposal_policy not in ("legacy_random", "matched_guided_v1")):
        raise ValueError("Invalid bounded training pipeline controls")
    gold_zip, root = Path(gold_zip), Path(root)
    if (gold_zip.is_symlink() or not gold_zip.is_file()
            or gold_zip.suffix.lower() != ".zip"
            or _digest(gold_zip) != SOURCE_SHA):
        raise ValueError("Expected original SHA-pinned private Gold archive")
    if gold_zip.resolve().is_relative_to(root.resolve()):
        raise ValueError("Source archive cannot be placed in research output")
    _safe_private_root(root)
    # Freeze relative CLI paths to absolute locations. The annual engine
    # changes cwd to the project root, and must still read the SAME private
    # source and write to the SAME outside-checkout output directory.
    gold_zip, root = gold_zip.resolve(strict=True), root.resolve()
    base = {"schema": SCHEMA, "source_sha256": SOURCE_SHA,
            "training_only": True, "independent_oos_proven": False,
            "live_trading_authorized": False, "historical_exposed": True}
    with exclusive_batch_lock(root):
        state = {**base, "status": "BOOTSTRAP_RUNNING",
                 "updated_utc": datetime.now(timezone.utc).isoformat()}
        _status(root, state)
        try:
            seed_result = bootstrap(gold_zip, root / "bootstrap", years=years,
                                    min_free_gb=min_free_gb)
            state["status"] = "CAMPAIGN_RUNNING"
            state["bootstrap"] = seed_result
            state["updated_utc"] = datetime.now(timezone.utc).isoformat()
            _status(root, state)
            campaign_result = campaign(
                Path(seed_result["seed"]), gold_zip, root / "campaign",
                seed=seed, generations=generations,
                proposal_count=proposal_count, shard_size=shard_size,
                min_free_gb=min_free_gb, max_wall_seconds=max_wall_seconds,
                proposal_policy=proposal_policy,
            )
            state["campaign"] = campaign_result
            complete = campaign_result["status"] == "COMPLETE_TRAINING_ONLY_NOT_OOS"
            paused = campaign_result["status"] in (
                "PAUSED_DISK_BUDGET", "PAUSED_TIME_BUDGET_BETWEEN_GENERATIONS"
            )
            finished = campaign_result["completed"]
            if not (complete or paused) or type(finished) is not list or (complete and not finished):
                raise ValueError("Unrecognized or empty completed research campaign")
            if finished:
                dashboard_path = root / "quant_research_dashboard.html"
                dashboard = build_dashboard(root / "campaign" / "cycles",
                                            dashboard_path)
                if (type(dashboard.get("generations")) is not int
                        or type(dashboard.get("verified_generations")) is not int
                        or dashboard["generations"] != len(finished)
                        or dashboard["verified_generations"] != len(finished)):
                    raise ValueError("Research dashboard has unverified generations")
                state["dashboard"] = {**dashboard, "path": str(dashboard_path)}
            else:
                state["dashboard"] = None
            state["status"] = (
                "COMPLETE_EXPOSED_TRAINING_PIPELINE_NOT_OOS"
                if campaign_result["status"] == "COMPLETE_TRAINING_ONLY_NOT_OOS"
                else "PAUSED_EXPOSED_TRAINING_PIPELINE_NOT_OOS"
            )
        except Exception as exc:
            state["status"] = "FAILED_REQUIRES_EVIDENCE_REVIEW"
            state["error_type"] = type(exc).__name__
            # Do not leak private filesystem paths or raw source details.
            state["updated_utc"] = datetime.now(timezone.utc).isoformat()
            _status(root, state)
            raise
        state["updated_utc"] = datetime.now(timezone.utc).isoformat()
        _status(root, state)
        return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--years", nargs="+", type=int, default=[2012, 2013])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--generations", type=int, default=10)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--shard-size", type=int, default=8)
    parser.add_argument("--min-free-gb", type=int, default=2)
    parser.add_argument("--max-wall-seconds", type=int, default=7200)
    parser.add_argument("--proposal-policy", default="legacy_random",
                        choices=("legacy_random", "matched_guided_v1"))
    args = parser.parse_args(argv)
    result = run_pipeline(
        args.gold_zip, args.out, years=args.years, seed=args.seed,
        generations=args.generations, proposal_count=args.count,
        shard_size=args.shard_size, min_free_gb=args.min_free_gb,
        max_wall_seconds=args.max_wall_seconds,
        proposal_policy=args.proposal_policy,
    )
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result["status"].startswith("COMPLETE") else 2


if __name__ == "__main__":
    raise SystemExit(main())
