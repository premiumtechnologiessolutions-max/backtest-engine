"""Bounded offline arithmetic research campaign with checkpoints and disk budgets.

This is a synchronous, manually invoked supervisor, NOT a remote daemon.
All private outputs remain outside Git. No live, OOS, or edge certification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

from scripts.run_arithmetic_research_cycles import run_cycles, _outside_checkout
from scripts.research_batch_orchestrator import exclusive_batch_lock
from scripts.materialize_arithmetic_generation import _load_strict
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA, _digest
from scripts.research_campaign_attestation import (
    freeze_campaign_intent, attest_cached_generation,
)

SCHEMA = "NRFX_ARITHMETIC_CAMPAIGN_V1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status(root: Path, content: dict) -> None:
    path = root / "campaign_status.json"
    if path.is_symlink():
        raise ValueError("Unsafe status symlink")
    payload = (json.dumps(content, sort_keys=True, indent=2, allow_nan=False)
               + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".campaign_status_", dir=root)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink():
            raise ValueError("Unsafe status symlink")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _verified_feedback(next_input: Path) -> str:
    if next_input.is_symlink():
        raise ValueError("Frozen input symlink refused")
    source, source_sha = _load_strict(next_input)
    sidecar = next_input.with_name(next_input.name + ".evidence.json")
    if sidecar.is_symlink():
        raise ValueError("Frozen evidence symlink refused")
    proof, _ = _load_strict(sidecar)
    if (type(source) is not dict or type(proof) is not dict
            or source.get("schema") != "NRFX_ARITHMETIC_TRAINING_INPUT_V1"
            or proof.get("schema") != "NRFX_ARITHMETIC_FEEDBACK_EVIDENCE_V1"
            or proof.get("next_input_sha256") != source_sha
            or proof.get("original_archive_sha256") != SOURCE_SHA
            or proof.get("training_only") is not True
            or proof.get("independent_oos_proven") is not False
            or proof.get("live_trading_authorized") is not False
            or proof.get("training_years") != source.get("years")
            or type(source.get("candidates")) is not list
            or not 1 <= len(source["candidates"]) <= 128):
        raise ValueError("Campaign feedback lacks frozen training provenance")
    return source_sha


def campaign(input_path: Path, source_zip: Path, root: Path, *,
             seed: int, first_generation: int = 1, generations: int = 10,
             proposal_count: int = 12, shard_size: int = 8,
             min_free_gb: int = 2, max_wall_seconds: int = 7200) -> dict:
    """Resume a bounded batch. Each completed generation is immutable.

    Runtime budget is observed BETWEEN generations; a single real M1 replay
    cannot be forcibly terminated safely by this wrapper.
    """
    controls = (seed, first_generation, generations, proposal_count,
                shard_size, min_free_gb, max_wall_seconds)
    if (any(type(x) is not int for x in controls)
            or seed < 0 or first_generation < 1
            or not 1 <= generations <= 200
            or not 1 <= proposal_count <= 128 or not 1 <= shard_size <= 128
            or not 0 <= min_free_gb <= 1024
            or not 60 <= max_wall_seconds <= 86400):
        raise ValueError("Invalid bounded research campaign controls")
    if (input_path.is_symlink() or not input_path.is_file()
            or source_zip.is_symlink() or not source_zip.is_file()
            or source_zip.suffix.lower() != ".zip"):
        raise ValueError("Original frozen input/Gold ZIP unavailable")
    if _digest(source_zip) != SOURCE_SHA:
        raise ValueError("Source Gold ZIP hash mismatch")
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        raise ValueError("Campaign root must be a real directory")
    _outside_checkout(root.resolve())
    if (input_path.resolve().is_relative_to(root.resolve())
            or source_zip.resolve().is_relative_to(root.resolve())):
        raise ValueError("Cannot overwrite original inputs with campaign")
    root.mkdir(parents=True, exist_ok=True)
    runs = root / "cycles"
    runs.mkdir(exist_ok=True)
    _outside_checkout(runs.resolve())
    begin = time.monotonic()
    with exclusive_batch_lock(root):
        freeze_campaign_intent(root, input_path, seed=seed,
                               first_generation=first_generation,
                               proposal_count=proposal_count,
                               shard_size=shard_size)
        current_input = input_path
        completed = []
        state = {"schema": SCHEMA, "started_utc": _now(),
                 "updated_utc": _now(), "status": "RUNNING_OBSERVED",
                 "first_generation": first_generation,
                 "requested_generations": generations, "completed": completed,
                 "training_only": True, "independent_oos_proven": False,
                 "live_trading_authorized": False}
        _status(root, state)
        try:
            for offset in range(generations):
                number = first_generation + offset
                if time.monotonic() - begin >= max_wall_seconds:
                    state["status"] = "PAUSED_TIME_BUDGET_BETWEEN_GENERATIONS"
                    break
                if shutil.disk_usage(root).free < min_free_gb * 1024 ** 3:
                    state["status"] = "PAUSED_DISK_BUDGET"
                    break
                next_input = runs / f"generation_{number:04d}" / "next_training_input.json"
                if next_input.exists():
                    provenance = attest_cached_generation(
                        current_input, next_input.parent,
                        generation=number, seed=seed + offset,
                        proposal_count=proposal_count)
                    fingerprint = _verified_feedback(next_input)
                    if provenance["next_input_sha256"] != fingerprint:
                        raise ValueError("Reaudited cached generation SHA mismatch")
                    status = "REUSED_FULLY_REAUDITED_FEEDBACK"
                else:
                    result = run_cycles(
                        current_input, source_zip, runs, seed=seed + offset,
                        first_generation=number, generations=1,
                        proposal_count=proposal_count, shard_size=shard_size)
                    if result["status"] != "COMPLETE_TRAINING_ONLY_NOT_OOS":
                        raise ValueError("Generation did not finish canonical training audit")
                    fingerprint = _verified_feedback(next_input)
                    status = "EXECUTED_AND_VERIFIED_FEEDBACK"
                completed.append({"generation": number,
                                  "status": status,
                                  "input_sha256": fingerprint})
                current_input = next_input
                state["updated_utc"] = _now()
                _status(root, state)
            else:
                state["status"] = "COMPLETE_TRAINING_ONLY_NOT_OOS"
        except Exception:
            state["status"] = "FAILED_REQUIRES_EVIDENCE_REVIEW"
            state["updated_utc"] = _now()
            _status(root, state)
            raise
        state["updated_utc"] = _now()
        _status(root, state)
        return state


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-input", required=True, type=Path)
    parser.add_argument("--gold-zip", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--first-generation", type=int, default=1)
    parser.add_argument("--generations", type=int, default=10)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--shard-size", type=int, default=8)
    parser.add_argument("--min-free-gb", type=int, default=2)
    parser.add_argument("--max-wall-seconds", type=int, default=7200)
    args = parser.parse_args(argv)
    result = campaign(args.training_input, args.gold_zip, args.out,
                      seed=args.seed, first_generation=args.first_generation,
                      generations=args.generations, proposal_count=args.count,
                      shard_size=args.shard_size, min_free_gb=args.min_free_gb,
                      max_wall_seconds=args.max_wall_seconds)
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
