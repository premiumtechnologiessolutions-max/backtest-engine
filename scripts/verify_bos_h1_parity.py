"""Compare the ACTUAL GitHub engine against independent archived gold trade ledgers.

Requires separately authorized private original Gold data.zip and the archived
standalone research results. Raw XAUUSD data must NOT be committed to GitHub.

Example:
  python scripts/verify_bos_h1_parity.py \
    --gold-zip "/secure/Gold data.zip" \
    --reference-root "/secure/nrf_bos_h1_validation" \
    --years 2012 2013 2014 2015 2016 2017 2018 2019 \
    --out "/secure/reports/bos_h1_parity.json"

For security, never download arbitrary inputs or execute anything from ZIP.
The original market-data archive is read as annual JSON only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from norisk_quant.bos_fib import BosFibSettings, bos_fib_limit_orders
from norisk_quant.data import load_market
from norisk_quant.h1_regime import filter_orders_h1
from norisk_quant.limit_engine import run_limits
from norisk_quant.model import Settings


EXPECTED_MARKET_SHA256 = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
FIELDS = {
    "signal_at": "signal_time",
    "entry_at": "entry_time",
    "closed_at": "exit_time",
    "side": "side",
    "entry_price": "entry",
    "exit_price": "exit",
    "stop": "stop",
    "target": "target",
    "gross_pnl": "gross",
    "cost": "fee",
    "net_pnl": "net",
    "exit_reason": "exit_reason",
    "gap_minutes": "gap_minutes",
}
TIMES = {"signal_at", "entry_at", "closed_at"}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as file:
        for buf in iter(lambda: file.read(8 * 1024 * 1024), b""):
            h.update(buf)
    return h.hexdigest()


def exact_ledger_check(ours: pd.DataFrame, reference: pd.DataFrame) -> dict:
    if len(ours) != len(reference):
        raise AssertionError(
            f"Trade count mismatch: actual={len(ours)} archived={len(reference)}"
        )
    if ours.empty:
        return {"trades": 0, "fields": len(FIELDS), "max_abs_pnl_delta": 0.0}
    for current, expected in FIELDS.items():
        if current not in ours or expected not in reference:
            raise AssertionError(f"Missing ledger field {current}/{expected}")
        if current in TIMES:
            lhs = pd.to_datetime(ours[current], utc=True).astype("int64").to_numpy() // 10**9
            rhs = reference[expected].to_numpy(dtype="int64")
            equals = np.array_equal(lhs, rhs)
        elif current == "exit_reason":
            equals = np.array_equal(
                ours[current].to_numpy(dtype=str),
                reference[expected].to_numpy(dtype=str),
            )
        else:
            equals = np.allclose(
                ours[current].to_numpy(dtype=float),
                reference[expected].to_numpy(dtype=float),
                rtol=0,
                atol=1e-7,
            )
        if not equals:
            raise AssertionError(f"First differing field: {current}")
    return {
        "trades": len(ours),
        "fields": len(FIELDS),
        "max_abs_pnl_delta": float(
            np.max(
                np.abs(
                    ours["net_pnl"].to_numpy(dtype=float)
                    - reference["net"].to_numpy(dtype=float)
                )
            )
        ),
    }


def verify(gold_zip: Path, reference_root: Path, years: list[int]) -> dict:
    sha = file_sha256(gold_zip)
    if sha != EXPECTED_MARKET_SHA256:
        raise ValueError("Dataset SHA-256 differs from archived reference gold source")
    yearly = pd.read_csv(reference_root / "yearly.csv")
    complete = []
    for year in years:
        # Read annual JSON only and don't allow unseen feed replacement.
        m1 = load_market(gold_zip, f"{year}-01-01", f"{year}-12-31")
        setups = bos_fib_limit_orders(m1, settings=BosFibSettings())
        h1_aligned = filter_orders_h1(m1, setups)
        variants = {
            "h1_only": h1_aligned,
            "h1_and_5x": [
                o for o in h1_aligned
                if abs(o.target - o.price) >= 5 * 0.40 - 1e-10
            ],
        }
        for name, orders in variants.items():
            result = run_limits(m1, orders, Settings(
                ounces=1.0, roundtrip_cost_per_ounce=0.40,
            ))
            baseline = pd.read_csv(
                reference_root / "results" / str(year) / name / "trades.csv"
            )
            check = exact_ledger_check(result.trades, baseline)
            summary_row = yearly.loc[
                (yearly["year"] == year) & (yearly["variant"] == name)
            ]
            if len(summary_row) != 1:
                raise AssertionError("Missing or duplicate year/variant reference")
            expected_count = int(summary_row.iloc[0]["trades"])
            expected_orders = int(summary_row.iloc[0]["orders"])
            if len(orders) != expected_orders or check["trades"] != expected_count:
                raise AssertionError("Signal count or trade count does not reconcile")
            total = float(result.trades["net_pnl"].sum())
            if not np.isclose(total, float(summary_row.iloc[0]["net_usd_oz"]), rtol=0, atol=1e-6):
                raise AssertionError("Annual P/L fails standalone reference reconciliation")
            complete.append({
                "year": year,
                "variant": name,
                "M1_rows": len(m1),
                "signals": len(orders),
                "net_usd_1oz": total,
                "deferred_same_entry_bar_TP": result.uncertain_entry_tp_deferred,
                **check,
                "status": "PASSED",
            })
    return {
        "status": "PASSED",
        "source_sha256": sha,
        "market": "XAUUSD synthetic BID-reference research",
        "execution_mode": "M1 stop-first, same-entry-bar TP deferred",
        "fixed_all_in_fee_usd_per_ounce": 0.40,
        "scenarios_verified": len(complete),
        "trades_matched": sum(x["trades"] for x in complete),
        "fields_per_trade": len(FIELDS),
        "limitations": "M1 cannot establish actual broker tick ordering or fills",
        "scenarios": complete,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--years", nargs="+", type=int, default=list(range(2012, 2020)))
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    output = verify(args.gold_zip, args.reference_root, args.years)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": output["status"],
        "years": args.years,
        "scenarios_verified": output["scenarios_verified"],
        "trades_matched": output["trades_matched"],
        "output": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
