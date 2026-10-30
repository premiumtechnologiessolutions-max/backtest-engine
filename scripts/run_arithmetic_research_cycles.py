"""Run bounded, immutable XAUUSD arithmetic research generations on private training data.

The only accepted source is the SHA-pinned local original ZIP. This is a
synchronous research runner, NOT an always-on agent, OOS proof or trader.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import os
import stat
import fcntl
from contextlib import contextmanager

from scripts.run_arithmetic_evolution import run as generate
from scripts.materialize_arithmetic_generation import materialize, _load_strict
from scripts.run_arithmetic_dispatch_training import (
    execute as replay, _digest, SOURCE_SHA,
)
from scripts.compile_arithmetic_training_feedback import (
    compile_feedback, _checked_index,
)


def _real_file(path: Path) -> Path:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Original research input must be a regular file")
    return path


def _real_directory(path: Path) -> Path:
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("Research output must be a real directory")
    for parent in path.parents:
        if parent.is_symlink():
            raise ValueError("Symlink research output ancestor forbidden")
    return path



@contextmanager
def _exclusive_research_lock(root: Path):
    """One nonblocking POSIX writer per private output root; no stale PID locks.

    The lock inode persists, but kernel flock is released even after crashes.
    Never unlink it: unlinking a live lock would permit a second writer.
    """
    lock = root / ".nrfx_research.lock"
    if lock.is_symlink():
        raise ValueError("Symlink research lock forbidden")
    try:
        fd = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600)
    except OSError as exc:
        raise ValueError("Cannot safely open research lock") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_mode & 0o077):
            raise ValueError("Research lock must be a private regular file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Research output root already has an active writer") from exc
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _prior_shard(directory: Path, dispatch: dict, year: int, start: int,
                 limit: int) -> None:
    """Only resume a complete matching shard; deep audit occurs in feedback."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Unsafe pre-existing replay shard")
    index, _ = _load_strict(directory / "training_replay_index.json")
    checked_year, rows = _checked_index(
        index, dispatch, set(dispatch["training_years"]),
        dispatch["training_input_sha256"])
    if (checked_year != year or index["requested_start_ordinal"] != start
            or index["requested_limit"] != limit
            or len(rows) != min(limit, dispatch["formula_count"] - start + 1)):
        raise ValueError("Pre-existing shard does not match frozen replay window")


def run_cycles(training_input: Path, source_zip: Path, output_root: Path, *,
               seed: int, first_generation: int, generations: int,
               proposal_count: int, shard_size: int = 8) -> dict:
    """Generate -> dispatch -> reference+fast training -> audit -> feedback.

    Each stage is immutable and resumable; a complete next input is only
    published by the canonical feedback verifier after all shards pass.
    """
    if (any(type(v) is not int for v in
            (seed, first_generation, generations, proposal_count, shard_size))
            or first_generation < 1 or not 1 <= generations <= 10
            or not 1 <= proposal_count <= 128 or not 1 <= shard_size <= 128):
        raise ValueError("Invalid bounded integer research controls")
    training_input, source_zip = _real_file(training_input), _real_file(source_zip)
    output_root = _real_directory(output_root)
    if source_zip.suffix.lower() != ".zip" or _digest(source_zip) != SOURCE_SHA:
        raise ValueError("Only the authorized original private Gold ZIP is accepted")
    root = output_root.resolve()
    if (training_input.resolve().is_relative_to(root)
            or source_zip.resolve().is_relative_to(root)
            or root.is_relative_to(training_input.resolve())
            or root.is_relative_to(source_zip.resolve())):
        raise ValueError("Research outputs must be separate from frozen inputs")
    output_root.mkdir(parents=True, exist_ok=True)
    with _exclusive_research_lock(output_root):
        initial_input = training_input
        completed = []
        for offset in range(generations):
            generation = first_generation + offset
            folder = _real_directory(output_root / f"generation_{generation:04d}")
            folder.mkdir(parents=True, exist_ok=True)
            manifest_path = folder / "generation.json"
            dispatch_dir = folder / "dispatch"
            next_input = folder / "next_training_input.json"
            generate(initial_input, manifest_path, seed=seed + offset,
                     generation=generation, proposal_count=proposal_count)
            dispatch = materialize(initial_input, manifest_path, dispatch_dir)
            shards = []
            for year in dispatch["training_years"]:
                for start in range(1, dispatch["formula_count"] + 1, shard_size):
                    limit = min(shard_size, dispatch["formula_count"] - start + 1)
                    dest = folder / f"replay_{year}_from_{start:03d}_count_{limit:03d}"
                    if dest.exists() or dest.is_symlink():
                        _prior_shard(dest, dispatch, year, start, limit)
                    else:
                        replay(initial_input, manifest_path, dispatch_dir,
                               source_zip, SOURCE_SHA, year, dest,
                               start_ordinal=start, limit=limit)
                    shards.append(dest)
            feedback = compile_feedback(initial_input, manifest_path,
                                        dispatch_dir, shards, next_input)
            if feedback["status"] != "COMPLETE_EXPOSED_TRAINING_FEEDBACK_NOT_OOS":
                raise ValueError("Annual feedback was not fully reconciled")
            completed.append({"generation": generation, "formula_count":
                              dispatch["formula_count"], "training_years":
                              dispatch["training_years"], "replay_shards": len(shards),
                              "next_input_sha256": feedback["next_input_sha256"]})
            initial_input = next_input
        return {"status": "COMPLETE_TRAINING_ONLY_NOT_OOS", "generations": completed,
                "last_training_input": str(initial_input),
                "independent_oos_proven": False, "live_trading_authorized": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-input", type=Path, required=True)
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--first-generation", type=int, default=1)
    parser.add_argument("--generations", type=int, default=1)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--shard-size", type=int, default=8)
    args = parser.parse_args(argv)
    result = run_cycles(args.training_input, args.gold_zip, args.out,
                        seed=args.seed, first_generation=args.first_generation,
                        generations=args.generations, proposal_count=args.count,
                        shard_size=args.shard_size)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
