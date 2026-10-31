#!/usr/bin/env python3
"""Fail-closed 2024 (or other full-year) parity gate for the ACTUAL package.

Runs reference and fast kernels against the SAME private source ZIP and
compares every executed trade, every observed M1 equity sample, and all
signal counts. Never uploads raw market data or trades to GitHub.
This is a parity gate, not a claim of tick-fill accuracy or profitability.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

from norisk_quant.accounting import validate_execution
from norisk_quant.data import load_market
from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.strategies_native import donchian_breakout_signals


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _comparison(label: str, expected: pd.DataFrame, observed: pd.DataFrame) -> dict:
    result = {"table": label, "reference_rows": len(expected), "fast_rows": len(observed)}
    try:
        pd.testing.assert_frame_equal(
            expected, observed, check_dtype=False,
            check_exact=False, rtol=0, atol=1e-9,
            check_freq=False,
        )
    except AssertionError as exc:
        result["status"] = "FAILED"
        result["reason"] = str(exc)[:2000]
    else:
        result["status"] = "PASSED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True, type=Path, help="PRIVATE Gold data.zip (never committed)")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--out", type=Path, default=Path("reports/generated/parity-2024.json"))
    args = parser.parse_args()
    if not args.zip.is_file() or args.zip.suffix.lower() != ".zip":
        parser.error("--zip must point to an existing local .zip")
    if not 2010 <= args.year <= 2026:
        parser.error("year outside available source range")
    settings = Settings(ounces=1, roundtrip_cost_per_ounce=0.40)
    data = load_market(args.zip, f"{args.year}-01-01", f"{args.year}-12-31")
    signals = donchian_breakout_signals(
        data, timeframe="H1", lookback=20, stop_distance=15, target_distance=30
    )
    reference = run(data, signals, settings)
    fast = run_fast(data, signals, settings)
    audit_ref = validate_execution(reference, settings)
    audit_fast = validate_execution(fast, settings)
    comparisons = [
        _comparison("trades", reference.trades, fast.trades),
        _comparison("equity_m1", reference.equity, fast.equity),
    ]
    counters = {
        "reference_pending": reference.pending_at_end,
        "fast_pending": fast.pending_at_end,
        "reference_expired": reference.expired_signals,
        "fast_expired": fast.expired_signals,
    }
    counters_match = (
        reference.pending_at_end == fast.pending_at_end
        and reference.expired_signals == fast.expired_signals
    )
    passed = all(c["status"] == "PASSED" for c in comparisons) and counters_match
    manifest = {
        "status": "PASSED" if passed else "FAILED",
        "meaning": "REFERENCE_FAST_PARITY_ONLY_NOT_BROKER_TICK_ACCURACY",
        "year": args.year,
        "source_sha256": _sha256(args.zip),
        "m1_rows": len(data),
        "first_observed_utc": data.index[0].isoformat(),
        "last_observed_utc": data.index[-1].isoformat(),
        "signal_count": len(signals),
        "fixed_all_in_usd_per_ounce": settings.roundtrip_cost_per_ounce,
        "reference_audit": audit_ref,
        "fast_audit": audit_fast,
        "comparisons": comparisons,
        "signal_counters": counters,
        "signal_counters_match": counters_match,
        "note": "Annual slicing may truncate open positions; continuous multi-year runs need a separate parity gate.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "status": manifest["status"], "year": args.year,
        "trades": len(reference.trades), "signals": len(signals),
        "output": str(args.out),
    }, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
