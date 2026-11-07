"""Offline CLI: reconcile private Gold M1 and optional OpenBB/FRED snapshot.

Only reads local files, never contacts brokers, exports quotes, or trades.
No FRED snapshot can be treated as historically released before its capture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from norisk_quant.data import fingerprint_loaded_m1, load_market, sha256_file
from norisk_quant.gold_macro_replay import research_state_at

SCHEMA = "NRFX_GOLD_MACRO_READONLY_CONTEXT_V1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_SNAPSHOT_BYTES = 1_000_000


def _read_fred(path: Path | None) -> dict | None:
    if path is None:
        return None
    path = Path(path)
    if (path.is_symlink() or not path.is_file()
            or path.suffix.lower() != ".json"
            or path.stat().st_size > _MAX_SNAPSHOT_BYTES):
        raise ValueError("Unsafe, missing or oversized frozen FRED snapshot")
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError("Duplicate frozen snapshot JSON fields")
            result[k] = v
        return result
    def no_constant(value):
        raise ValueError("Nonfinite frozen FRED JSON value")
    parsed = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=unique,
        parse_constant=no_constant)
    if type(parsed) is not dict:
        raise ValueError("FRED snapshot must be a JSON object")
    return parsed


def read_local_context(gold_zip: Path, *, source_sha256: str,
                       start: str, end: str, decision_at: str,
                       fred_snapshot_path: Path | None = None) -> dict:
    """Execute real Gold ZIP source validation and read-only causal inspection."""
    gold_zip = Path(gold_zip)
    if (gold_zip.is_symlink() or not gold_zip.is_file()
            or gold_zip.suffix.lower() != ".zip"
            or type(source_sha256) is not str
            or not _SHA.fullmatch(source_sha256)):
        raise ValueError("Expected SHA-pinned private annual Gold ZIP")
    if sha256_file(gold_zip) != source_sha256:
        raise ValueError("Gold ZIP original source SHA256 mismatch")
    # Fail on bad external JSON *before* touching expensive market data.
    frozen_fred = _read_fred(fred_snapshot_path)
    # load_market() uses exact UTC calendar days and the original Bid/Ask M1
    # geometry; it does NOT fill missing minutes or claim broker tick parity.
    frame = load_market(gold_zip, start, end)
    fingerprint = fingerprint_loaded_m1(frame)
    state = research_state_at(
        frame, expected_loaded_fingerprint=fingerprint,
        decision_at=decision_at, fred_snapshot=frozen_fred)
    return {
        "schema": SCHEMA,
        "source_zip_sha256": source_sha256,
        "loaded_m1_fingerprint": fingerprint,
        "loaded_bars": len(frame),
        "start_date": start, "end_date": end,
        "context": state,
        "status": "READ_ONLY_CAUSAL_RESEARCH_NOT_ACCEPTED",
        "original_execution_13_field_parity_verified": False,
        "broker_fill_parity_verified": False,
        "prospective_oos_proven": False,
        "live_trading_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--decision-at", required=True)
    parser.add_argument("--fred-snapshot", type=Path)
    args = parser.parse_args(argv)
    result = read_local_context(
        args.gold_zip, source_sha256=args.source_sha256,
        start=args.start, end=args.end, decision_at=args.decision_at,
        fred_snapshot_path=args.fred_snapshot)
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
