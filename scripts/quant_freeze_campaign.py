"""Freeze a quant campaign design safely; NEVER execute research.

CLI connects a local construction specification to the sharded DAG and
the read-only mission-control dashboard. No Gold archives, external
providers, AI models, worker processes or broker endpoints are opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from norisk_quant.campaign_sharding import (
    freeze_sharded_campaign, verify_sharded_campaign,
)

_MAX_SPEC_BYTES = 2_097_152
_MAX_DESIGN_BYTES = 64 * 1024 * 1024


def _read_spec(path: Path) -> dict:
    if (path.is_symlink() or not path.is_file()
            or path.suffix.lower() != ".json"
            or path.stat().st_size > _MAX_SPEC_BYTES):
        raise ValueError("Unsafe or oversized construction specification")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_SPEC_BYTES:
            raise ValueError("Unsafe construction source file")
        raw = stream.read(_MAX_SPEC_BYTES + 1)
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("Duplicate construction spec JSON key")
            obj[key] = value
        return obj
    def reject_constant(value):
        raise ValueError("Nonfinite construction spec value")
    parsed = json.loads(raw, object_pairs_hook=unique, parse_constant=reject_constant)
    if type(parsed) is not dict:
        raise ValueError("Construction spec must be a JSON object")
    return parsed


def _durable_publish(target: Path, raw: bytes) -> str:
    if len(raw) > _MAX_DESIGN_BYTES:
        raise ValueError("Frozen design exceeds bounded output")
    if (target.suffix.lower() != ".json"
            or not target.parent.is_dir()
            or target.parent.is_symlink()
            or target.is_symlink()):
        raise ValueError("Unsafe frozen design destination")
    digest = hashlib.sha256(raw).hexdigest()
    if target.exists():
        if target.read_bytes() != raw:
            raise ValueError("Immutable frozen design cannot be overwritten")
        return "ALREADY_FROZEN_IDENTICAL"
    fd, temp_name = tempfile.mkstemp(
        prefix=".quant-design-", suffix=".tmp", dir=target.parent)
    staged = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            if os.name == "posix":
                os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # Hard-link publish is atomic and fails if destination already
            # exists; os.replace would silently clobber a frozen file.
            os.link(staged, target)
            state = "FROZEN_CONSTRUCTION_DESIGN_ONLY"
        except FileExistsError:
            if target.is_symlink() or target.read_bytes() != raw:
                raise ValueError("Concurrent conflicting frozen design publication")
            state = "ALREADY_FROZEN_IDENTICAL"
        if os.name == "posix":
            dfd = os.open(target.parent, os.O_RDONLY |
                          getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        return state
    finally:
        staged.unlink(missing_ok=True)


def freeze_local_spec(spec_path: Path, output_path: Path) -> dict:
    """Safely produce an immutable, inert construction artifact."""
    spec_path, output_path = Path(spec_path), Path(output_path)
    compiled = freeze_sharded_campaign(_read_spec(spec_path))
    verify_sharded_campaign(compiled)
    raw = (json.dumps(compiled, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    status = _durable_publish(output_path, raw)
    return {
        "schema": "NRFX_QUANT_CONSTRUCTION_FREEZE_RESULT_V1",
        "status": status,
        "sharded_blueprint_sha256": compiled["sharded_blueprint_sha256"],
        "file_sha256": hashlib.sha256(raw).hexdigest(),
        "strategies": compiled["strategy_count"],
        "shards": compiled["shard_count"],
        "nodes": compiled["total_designed_nodes"],
        "market_data_opened": False,
        "worker_started": False,
        "research_result_accepted": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spec", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args(argv)
    summary = freeze_local_spec(args.spec, args.out)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
