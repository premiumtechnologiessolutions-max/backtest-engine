"""Frozen NYM-01 08:20 New York morning research on private source data.

Design years 2012 and 2013, no parameter tuning. Two DISTINCT candidate
hypotheses are reported separately; never sum them as a portfolio.
Original private ZIP/trade ledgers never uploaded to public CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from norisk_quant.data import sha256_file, load_market, fingerprint_loaded_m1
from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.ny_morning import NewYorkOpenSettings, ny_open_signals
from norisk_quant.report import report

SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
DESIGN_YEARS = (2012, 2013)
CANDIDATES = {
    "breakout": NewYorkOpenSettings(variant="breakout"),
    "rejection": NewYorkOpenSettings(variant="rejection"),
}
EXECUTION = Settings(
    ounces=1.0, roundtrip_cost_per_ounce=0.40,
    max_entry_delay_minutes=1, max_holding_minutes=180,
)
SPEC = {
    "research_id": "NYM-01",
    "original_source_sha": SOURCE_SHA,
    "NY_range_local": "08:20–09:00 America/New_York",
    "signal_M5_closing_local": "09:05–11:00",
    "stage1_years": list(DESIGN_YEARS),
    "candidate_settings": {k: vars(v) for k, v in CANDIDATES.items()},
    "execution": {
        "one_ounce": 1, "all_in_cost_usd_per_ounce": 0.40,
        "max_holding_minutes": 180, "max_entry_delay_minutes": 1,
        "M1_stop_first": True, "gap_through": True,
    },
    "promotion_threshold": "at least 16/24 positive months, total net>0, >=50 trades each year",
    "independent_out_of_sample": False,
}
SPEC_SHA = hashlib.sha256(json.dumps(
    SPEC, sort_keys=True, separators=(",", ":")
).encode()).hexdigest()


def execute(gold_zip: Path, year: int, out: Path) -> dict:
    if type(year) is not int or year not in DESIGN_YEARS:
        raise ValueError("NYM-01 stage-1 only permits preregistered 2012 and 2013")
    if sha256_file(gold_zip) != SOURCE_SHA:
        raise ValueError("Original Gold data ZIP SHA mismatch")
    if any((out / x / "summary.json").exists() for x in CANDIDATES):
        raise FileExistsError("Use a new versioned output directory; no overwrites")
    bars = load_market(gold_zip, f"{year}-01-01", f"{year}-12-31")
    loaded_sha = fingerprint_loaded_m1(bars)
    record = {
        "year": year, "status": "DESIGN_ONLY_NOT_OOS",
        "original_source_sha256": SOURCE_SHA, "loaded_m1_sha256": loaded_sha,
        "m1_rows": len(bars), "spec_sha256": SPEC_SHA, "candidates": {},
    }
    for variant, cfg in CANDIDATES.items():
        signals = ny_open_signals(bars, settings=cfg)
        reference = run(bars, signals, EXECUTION)
        fast = run_fast(bars, signals, EXECUTION)
        pd.testing.assert_frame_equal(
            reference.trades, fast.trades, check_dtype=False,
            check_exact=False, atol=1e-7, rtol=0,
        )
        result = report(reference, EXECUTION, out / variant,
                        source="authenticated_original_private_gold_source",
                        provenance={"source_archive_sha256": SOURCE_SHA,
                                    "loaded_m1_bidask_sha256": loaded_sha},
                        run_parameters={"ny_morning_spec_sha256": SPEC_SHA,
                                        "variant": variant})
        if result["months_observed"] != 12 or result["months_with_m1_observations"] != 12:
            raise AssertionError("Design year is missing month coverage")
        if abs(result["total_fees"] - 0.4 * result["trades"]) > 1e-7:
            raise AssertionError("Fee accounting deviates from exactly $0.40/oz")
        record["candidates"][variant] = {
            "signals": len(signals), "trades": result["trades"],
            "positive_months": result["positive_months"],
            "net_usd_oz": result["net_pnl"],
            "max_m1_drawdown": result["max_drawdown_observed_m1"],
            "total_fees": result["total_fees"],
            "reference_fast_parity": "PASSED",
        }
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(SPEC, indent=2), encoding="utf-8")
    (out / "scoreboard.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-zip", required=True, type=Path)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(execute(args.gold_zip, args.year, args.out), indent=2))


if __name__ == "__main__":
    main()
