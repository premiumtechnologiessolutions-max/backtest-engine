"""Offline private XAUUSD M1 data + immutable agent-proposal preflight.

Only direct original JSON/CSV Bid/Ask M1 sources are supported in this first
lineage gate. Original multi-year ZIP/Parquet import lineage is a separate gate.
Never executes a strategy, connects MT5, prints quote values or private hashes.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from norisk_quant.research_source_loader import preflight_direct_gold_m1_file
from norisk_quant.research_source_preflight import inspect_local_checkout


def _private_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 32_768:
        raise ValueError("Private source metadata must be regular and bounded")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Ambiguous duplicate key in research evidence")
            result[key] = value
        return result
    def reject_constant(_):
        raise ValueError("Research evidence cannot contain nonfinite values")
    def finite_float(value):
        num = float(value)
        if not math.isfinite(num):
            raise ValueError("Research evidence cannot contain nonfinite number")
        return num
    try:
        item = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=reject_constant, parse_float=finite_float)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed private JSON evidence") from exc
    if type(item) is not dict:
        raise ValueError("Expected one research metadata object")
    return item


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--original-m1", type=Path, required=True)
    parser.add_argument("--checkout", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        proposal = _private_json(args.proposal)
        manifest = _private_json(args.source_manifest)
        head = inspect_local_checkout(args.checkout)
        result = preflight_direct_gold_m1_file(
            proposal, manifest, original_m1_file=args.original_m1,
            observed_engine_commit=head,
        )
    except (OSError, ValueError, KeyError, TypeError):
        # Refuse to echo private file paths, raw data or attacker-supplied text.
        parser.exit(2, "Private research source preflight rejected; no experiment executed.\n")
    print(json.dumps(result.public_metadata(), sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
