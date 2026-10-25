"""Frozen QS01 design-only replay using private original Gold data.zip.

This script NEVER fetches, uploads, or commits raw quote data. It refuses any
archive except the exact authorized original and does NOT touch 2017-2026.
No parameter optimization or trading is performed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from norisk_quant.data import load_market, sha256_file, fingerprint_loaded_m1
from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.qs01 import qs01_signals
from norisk_quant.report import report

SOURCE_SHA256 = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
DESIGN_START = "2012-01-01"
DESIGN_END = "2016-12-31"
FROZEN = Settings(
    ounces=1.0, roundtrip_cost_per_ounce=0.40,
    max_entry_delay_minutes=0, max_hold_minutes=30, close_at_end=True,
)


def execute(gold_zip: Path, out: Path, *, execution: str = "reference") -> dict:
    if execution not in ("reference", "fast"):
        raise ValueError("Execution must be reference or fast")
    if not gold_zip.is_file() or gold_zip.suffix.lower() != ".zip":
        raise ValueError("Private original Gold data.zip is required")
    actual_sha = sha256_file(gold_zip)
    if actual_sha != SOURCE_SHA256:
        raise ValueError("Source archive SHA mismatch; refuse substituted quotes")
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Destination must be empty; never overwrite audit runs")
    data = load_market(gold_zip, DESIGN_START, DESIGN_END)
    if data.index.min().year != 2012 or data.index.max().year != 2016:
        raise ValueError("Design source missing one or more boundary years")
    signals = qs01_signals(data)
    engine = run if execution == "reference" else run_fast
    result = engine(data, signals, FROZEN)
    summary = report(
        result, FROZEN, out,
        source="original_private_Gold_data.zip",
        provenance={
            "source_archive_sha256": actual_sha,
            "loaded_m1_bidask_sha256": fingerprint_loaded_m1(data),
            "loaded_m1_rows": len(data),
        },
        run_parameters={
            "strategy": "QS01_quote_stress_exhaustion_frozen_2026-10-25",
            "evaluation_role": "DESIGN_2012_2016_ONLY",
            "execution": execution,
            "no_exposed_period_selection": True,
            "cost": "FIXED_ALL_IN_USD_0.40_PER_OUNCE_ROUNDTRIP",
        },
    )
    trades = result.trades
    if summary["months_observed"] != 60 or summary["months_with_m1_observations"] != 60:
        raise AssertionError("QS01 design requires 60 calendar months WITH observed M1 quotes")
    net = float(trades["net_pnl"].sum()) if len(trades) else 0.0
    if abs(net - summary["net_pnl"]) > 1e-7:
        raise AssertionError("Executed trade ledger and report net differ")
    if abs(float(trades["cost"].sum()) - .40 * len(trades)) > 1e-7:
        raise AssertionError("Canonical ALL-IN fees mismatch")
    monthly = pd.read_csv(out / "monthly.csv")
    weekly = pd.read_csv(out / "weekly.csv")
    if abs(float(monthly["net_pnl"].sum()) - net) > 1e-7:
        raise AssertionError("Monthly reconciliation mismatch")
    if abs(float(weekly["net_pnl"].sum()) - net) > 1e-7:
        raise AssertionError("Weekly reconciliation mismatch")
    pf = summary["profit_factor"]
    accepted = bool(
        summary["trades"] >= 200 and summary["net_pnl"] > 0
        and pf is not None and pf > 1.10 and summary["positive_months"] >= 31
    )
    decision = {
        "strategy": "QS01_quote_stress_exhaustion",
        "status": "DESIGN_SCREEN_PASS_NOT_OOS" if accepted else "REJECT_DESIGN",
        "eligible_for_chronological_2017_2019_validation": accepted,
        "design_start": DESIGN_START,
        "design_end": DESIGN_END,
        "trades": summary["trades"],
        "positive_months": summary["positive_months"],
        "months": summary["months_observed"],
        "net_usd_per_ounce": summary["net_pnl"],
        "profit_factor": pf,
        "max_observed_m1_drawdown_usd_per_ounce": summary["max_drawdown_observed_m1"],
        "source_archive_sha256": actual_sha,
        "loaded_m1_bidask_sha256": fingerprint_loaded_m1(data),
        "execution": execution,
        "do_not_claim_clean_oos": True,
        "historical_tick_reconstruction": False,
    }
    (out / "frozen_design_decision.json").write_text(
        json.dumps(decision, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return decision


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-zip", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--execution", choices=("reference", "fast"), default="reference")
    args = parser.parse_args()
    print(json.dumps(execute(args.gold_zip, args.out, execution=args.execution),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
