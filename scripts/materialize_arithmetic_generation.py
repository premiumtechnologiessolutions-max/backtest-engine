"""Verify frozen training evolution and publish canonical CLI formula files.

This is a research dispatch bridge, NOT a backtest, OOS proof, or live trader.
The original training input is required: a self-consistent manifest hash alone
is not sufficient to authenticate a generated evolution result.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from norisk_quant.research_evolution import evolve_training_generation
from scripts.run_arithmetic_evolution import SCHEMA, _reject_constant, _unique_pairs

DISPATCH_SCHEMA = "NRFX_ARITHMETIC_DISPATCH_V1"
MAX_INPUT_BYTES = 16 * 1024 * 1024


def _load_strict(path: Path):
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_INPUT_BYTES:
        raise ValueError("Empty or oversized frozen JSON evidence")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                      parse_constant=_reject_constant)
    return data, sha256(raw).hexdigest()


def _encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)
            + "\n").encode("utf-8")


def _verified_generation(training_input: Path, generation_manifest: Path):
    source, input_sha = _load_strict(training_input)
    envelope, _ = _load_strict(generation_manifest)
    if (type(source) is not dict or set(source) != {
            "schema", "years", "candidates", "explored_ids"}
            or source["schema"] != SCHEMA
            or type(source["years"]) is not list
            or type(source["explored_ids"]) is not list):
        raise ValueError("Unexpected frozen training input schema")
    if (type(envelope) is not dict
            or set(envelope) != {"input_sha256", "result"}
            or envelope["input_sha256"] != input_sha
            or type(envelope["result"]) is not dict):
        raise ValueError("Generation does not match frozen training input")
    result = envelope["result"]
    if (type(result.get("seed")) is not int
            or type(result.get("generation")) is not int
            or type(result.get("proposals")) is not list
            or not 1 <= len(result["proposals"]) <= 128):
        raise ValueError("Invalid frozen evolution controls")
    expected = evolve_training_generation(
        source["candidates"], tuple(source["years"]),
        seed=result["seed"], generation=result["generation"],
        proposal_count=len(result["proposals"]),
        explored_ids=tuple(source["explored_ids"]))
    if result != expected:
        raise ValueError("Evolution manifest fails deterministic training replay")
    return expected, input_sha


def _publish_once(path: Path, data: bytes) -> None:
    if path.is_symlink():
        raise ValueError(f"Symlink output rejected: {path.name}")
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError(f"Existing evidence differs: {path.name}")
        return
    fd, temporary = tempfile.mkstemp(prefix=".nrfx_dispatch_", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)  # exclusive: never replace existing evidence
        except FileExistsError:
            if (path.is_symlink() or not path.is_file()
                    or path.read_bytes() != data):
                raise ValueError(f"Concurrent evidence differs: {path.name}")
    finally:
        Path(temporary).unlink(missing_ok=True)


def materialize(training_input: Path, generation_manifest: Path,
                output_dir: Path) -> dict:
    """Replay and verify generation before writing any research dispatch files.

    Repeated calls are idempotent; an interrupted publish may resume, but no
    existing formula, index, symlink, or unexpected file can be overwritten.
    """
    result, input_sha = _verified_generation(training_input, generation_manifest)
    if output_dir.is_symlink() or (output_dir.exists() and not output_dir.is_dir()):
        raise ValueError("Dispatch output must be a real directory")
    files = {}
    entries = []
    for index, proposal in enumerate(result["proposals"], 1):
        name = f"formula_{index:03d}_{proposal['identity'][:16]}.json"
        data = _encoded(proposal["formula"])
        files[name] = data
        entries.append({
            "ordinal": index, "identity": proposal["identity"],
            "parent_identity": proposal["parent_identity"],
            "relative_path": name,
            "file_sha256": sha256(data).hexdigest(),
        })
    dispatch = {
        "schema": DISPATCH_SCHEMA,
        "training_input_sha256": input_sha,
        "generation_manifest_sha256": result["manifest_sha256"],
        "generation": result["generation"],
        "training_years": result["training_years"],
        "formula_count": len(entries), "formulas": entries,
        "execution_contract": {"strategy": "arithmetic", "timeframe": "M1",
                               "all_in_cost_per_ounce": 0.40,
                               "backtests_executed": False},
        "independent_oos_proven": False, "live_trading_authorized": False,
    }
    files["dispatch_index.json"] = _encoded(dispatch)
    # Verify the entire existing directory before writing anything new.
    if output_dir.exists():
        unexpected = {p.name for p in output_dir.iterdir()} - set(files)
        if unexpected:
            raise ValueError("Unexpected files in frozen dispatch directory")
        for name, data in files.items():
            path = output_dir / name
            if path.is_symlink() or (path.exists() and
                    (not path.is_file() or path.read_bytes() != data)):
                raise ValueError(f"Existing evidence differs: {name}")
    else:
        output_dir.mkdir(parents=True, exist_ok=False)
    # The index is the last file published: absence signals partial output.
    for name, data in files.items():
        if name != "dispatch_index.json":
            _publish_once(output_dir / name, data)
    _publish_once(output_dir / "dispatch_index.json",
                  files["dispatch_index.json"])
    return dispatch


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-input", type=Path, required=True)
    parser.add_argument("--generation-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    dispatch = materialize(args.training_input, args.generation_manifest,
                           args.output_dir)
    print(f"Verified training-only dispatch: {dispatch['formula_count']} formulas; "
          f"manifest {dispatch['generation_manifest_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
