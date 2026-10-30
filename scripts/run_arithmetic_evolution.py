"""Offline, fail-closed training-only arithmetic generation CLI.

Input is a frozen JSON summary of reconciled TRAINING years, never raw quotes.
No network, no broker calls, no prospective/holdout data and no edge claims.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from norisk_quant.research_evolution import evolve_training_generation

SCHEMA = "NRFX_ARITHMETIC_TRAINING_INPUT_V1"


def _unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON key rejected")
        obj[key] = value
    return obj


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON value rejected: {value}")


def run(input_path: Path, output_path: Path, *, seed: int, generation: int,
        proposal_count: int, proposal_policy: str = "legacy_random") -> dict:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output must be different files")
    raw = input_path.read_bytes()
    if not raw or len(raw) > 16 * 1024 * 1024:
        raise ValueError("Empty or oversized frozen training input")
    source = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                        parse_constant=_reject_constant)
    if type(source) is not dict or set(source) != {
            "schema", "years", "candidates", "explored_ids"} or source["schema"] != SCHEMA:
        raise ValueError("Unexpected training input envelope")
    if type(source["years"]) is not list or type(source["explored_ids"]) is not list:
        raise ValueError("Training years and explored IDs must be JSON arrays")
    result = evolve_training_generation(
        source["candidates"], tuple(source["years"]), seed=seed,
        generation=generation, proposal_count=proposal_count,
        explored_ids=tuple(source["explored_ids"]),
        proposal_policy=proposal_policy)
    envelope = {"input_sha256": sha256(raw).hexdigest(), "result": result}
    content = (json.dumps(envelope, sort_keys=True, indent=2, allow_nan=False)
               + "\n").encode("utf-8")
    if output_path.exists():
        if output_path.is_symlink() or output_path.read_bytes() != content:
            raise ValueError("Existing output differs: refusing to overwrite research evidence")
        return envelope
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".nrfx_evolution_", suffix=".tmp",
                                     dir=output_path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Exclusive hard-link publish avoids replacing an existing result.
        try:
            os.link(temporary, output_path)
        except FileExistsError:
            if output_path.read_bytes() != content:
                raise ValueError("Concurrent output differs: refusing overwrite")
    finally:
        Path(temporary).unlink(missing_ok=True)
    return envelope


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--generation", type=int, required=True)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--proposal-policy", choices=("legacy_random", "matched_guided_v1"),
                        default="legacy_random")
    args = parser.parse_args(argv)
    envelope = run(args.input, args.output, seed=args.seed,
                   generation=args.generation, proposal_count=args.count, proposal_policy=args.proposal_policy)
    print(f"Training-only proposals: {len(envelope['result']['proposals'])}; "
          f"manifest SHA256: {envelope['result']['manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
