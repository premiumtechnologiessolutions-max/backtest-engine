"""Run predeclared CEB-01 design years on PRIVATE original XAUUSD ZIP.

Stage-1 years 2012 and 2013 only. The public repo/Actions must never
receive the source ZIP or yearly M1/trade ledgers. Reference and fast
Market engines must match before any result is reported as evaluated.

Example:
 PYTHONPATH=src python -m scripts.run_frozen_compression \
   --gold-zip "/secure/Gold data.zip" --year 2012 --out "/secure/CEB-01-2012"
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from norisk_quant.compression_breakout import (
    CompressionSettings, compression_breakout_signals,
)
from norisk_quant.data import fingerprint_loaded_m1, load_market, sha256_file
from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.report import report

EXPECTED_ZIP_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
DESIGN_YEARS = (2012, 2013)
CANDIDATES = {
    "M15": CompressionSettings(timeframe="M15"),
    "H1": CompressionSettings(timeframe="H1"),
}
FIXED_EXECUTION = Settings(ounces=1.0, roundtrip_cost_per_ounce=0.40)
SERIALIZED_SPEC = {
    "research_id": "CEB-01",
    "predeclared_design_years": list(DESIGN_YEARS),
    "strategy": {
        timeframe: vars(settings)
        for timeframe, settings in CANDIDATES.items()
    },
    "execution": {
        "ounces": 1.0,
        "all_in_roundtrip_fee_per_ounce": 0.40,
        "stop_first": True,
        "gap_through": True,
        "initial_signal": "fully_closed_candle",
    },
    "stage_1": "2012,2013 separately; positive net, >=16/24 positive months and >=50 trades per year",
    "independence": "HISTORICALLY_EXPOSED_DESIGN_NOT_OOS",
}
SPEC_SHA = hashlib.sha256(json.dumps(
    SERIALIZED_SPEC, sort_keys=True, separators=(",", ":")
).encode()).hexdigest()


def execute(gold_zip: Path, year: int, out: Path) -> dict:
    if type(year) is not int or year not in DESIGN_YEARS:
        raise ValueError("CEB-01 stage-1 frozen to design years 2012 and 2013")
    if sha256_file(gold_zip) != EXPECTED_ZIP_SHA:
        raise ValueError("Original private source SHA-256 mismatch")
    if any((out / tf / "summary.json").exists() for tf in CANDIDATES):
        raise FileExistsError("Research outputs exist: use another versioned folder")
    bars = load_market(gold_zip, f"{year}-01-01", f"{year}-12-31")
    audit = {
        "status": "DESIGN_ONLY_NOT_OOS", "year": year,
        "source_sha256": EXPECTED_ZIP_SHA,
        "loaded_m1_sha256": fingerprint_loaded_m1(bars),
        "m1_rows": len(bars), "spec_sha256": SPEC_SHA,
        "candidates": {},
    }
    for timeframe, params in CANDIDATES.items():
        signals = compression_breakout_signals(bars, settings=params)
        reference = run(bars, signals, FIXED_EXECUTION)
        fast = run_fast(bars, signals, FIXED_EXECUTION)
        pd.testing.assert_frame_equal(
            reference.trades, fast.trades, check_dtype=False,
            check_exact=False, atol=1e-7, rtol=0,
        )
        output = out / timeframe
        summary = report(reference, FIXED_EXECUTION, output,
                         source="private_source_sha256_authenticated",
                         provenance={"source_zip_sha256": EXPECTED_ZIP_SHA,
                                     "loaded_m1_sha256": audit["loaded_m1_sha256"]},
                         run_parameters={"candidate_spec_sha256": SPEC_SHA,
                                         "timeframe": timeframe})
        if summary["months_observed"] != 12 or summary["months_with_m1_observations"] != 12:
            raise AssertionError("The frozen 12-calendar-month design ledger is incomplete")
        if summary["total_fees"] != round(0.40 * summary["trades"], 8):
            if abs(summary["total_fees"] - 0.40 * summary["trades"]) > 1e-7:
                raise AssertionError("Fee reconciliation failed")
        audit["candidates"][timeframe] = {
            "signals": len(signals), "trades": summary["trades"],
            "net_usd_oz": summary["net_pnl"],
            "positive_months": summary["positive_months"],
            "max_m1_drawdown": summary["max_drawdown_observed_m1"],
            "total_fees": summary["total_fees"],
            "reference_fast_execution_parity": "PASSED",
            "synthetic_bid_reference_not_actual_broker_fills": True,
        }
    out.mkdir(parents=True, exist_ok=True)
    (out / "frozen_spec.json").write_text(
        json.dumps(SERIALIZED_SPEC, indent=2), encoding="utf-8"
    )
    (out / "year_scoreboard.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(execute(args.gold_zip, args.year, args.out), indent=2))


if __name__ == "__main__":
    main()
