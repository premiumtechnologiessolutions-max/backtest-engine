"""Locked FAC011 chronology stress, 2014–2016 only, no retuning.

Preregistered at 34bec248970622dce568e5e7fe95cde4a6ad2bb5
before reading 2014–2016 FAC011 outcomes. Historical exposure != clean OOS.
Private Gold ZIP stays local; never upload source quotes to GitHub Actions.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

from norisk_quant.data import fingerprint_loaded_m1, load_market, sha256_file
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.strategy import aggregate_bars
from scripts.batch_donchian_grid import ORIGINAL, replay_core
from scripts.batch_directional_run_h1_grid import (
    directional_run_signals, causal_filters, filtered_signals, canonical_signals,
)

LOCKED_ID = "RUN15_N3_K3.00_FOLLOW_HOT_ALL_SL3.00_TP6.00"
PREREG = "34bec248970622dce568e5e7fe95cde4a6ad2bb5"


def replay_locked(m1, year: int):
    if type(year) is not int or year not in (2014, 2015, 2016):
        raise ValueError("Only locked chronological stress years")
    m15, h1 = aggregate_bars(m1, "M15"), aggregate_bars(m1, "H1")
    base_t, base_s = directional_run_signals(m15, 3, 3.)
    times, regimes, sessions = causal_filters(m15, h1)
    st, sd = filtered_signals(base_t, base_s, times, regimes, sessions,
                              "FOLLOW", "HOT", "ALL")
    stamps = np.asarray(m1.index.asi8 // 1_000_000_000, dtype=np.int64)
    op, hi, lo, cl = (m1[k].to_numpy(dtype=float) for k in ("o", "h", "l", "c"))
    months = (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8)
    monthly, trades, net, fees, dd, expired = replay_core(
        stamps, op, hi, lo, cl, months, st, sd, 3., 6.)
    canonical = run_fast(
        m1, canonical_signals(st, sd, 3., 6.),
        Settings(ounces=1., roundtrip_cost_per_ounce=.4))
    ref_month = np.bincount(
        pd.to_datetime(canonical.trades.closed_at, utc=True).dt.month,
        weights=canonical.trades.net_pnl.to_numpy(), minlength=13)[1:]
    equity = canonical.equity.equity
    ref_dd = float((equity.cummax().clip(lower=0) - equity).clip(lower=0).max())
    month_delta = float(np.max(np.abs(ref_month - monthly)))
    dd_delta = abs(ref_dd - dd)
    if (month_delta > 1e-7 or dd_delta > 1e-7
            or abs(net - canonical.trades.net_pnl.sum()) > 1e-7
            or abs(fees - canonical.trades.cost.sum()) > 1e-7
            or len(canonical.trades) != trades):
        raise AssertionError("Official canonical parity failed")
    return {
        "year": year, "m1_rows": len(m1),
        "loaded_m1_sha256": fingerprint_loaded_m1(m1),
        "signals": len(st), "expired": int(expired), "trades": int(trades),
        "net_usd_oz": float(net), "fees_usd": float(fees),
        "gross_usd_oz": float(net + fees),
        "max_m1_floating_dd": float(dd),
        "positive_months": int((monthly > 0).sum()),
        "worst_month": float(monthly.min()),
        "monthly_exit_booked_usd_oz": [float(x) for x in monthly],
        "canonical_month_delta": month_delta,
        "canonical_floating_dd_delta": dd_delta,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gold-zip", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if sha256_file(args.gold_zip) != ORIGINAL:
        raise ValueError("Private original source SHA mismatch")
    if args.out.exists():
        raise FileExistsError("Refuse to overwrite locked experiment")
    results = []
    for year in (2014, 2015, 2016):
        m1 = load_market(args.gold_zip, f"{year}-01-01", f"{year}-12-31")
        results.append(replay_locked(m1, year))
    positive = sum(row["positive_months"] for row in results)
    passed = positive >= 27 and all(
        row["net_usd_oz"] > 0 and row["trades"] >= 80
        and row["worst_month"] >= -20
        and row["max_m1_floating_dd"] <= 100 for row in results)
    payload = {
        "research_id": "NRF-FAC-011-LOCK", "candidate": LOCKED_ID,
        "preregistration_commit": PREREG, "source_sha256": ORIGINAL,
        "historically_exposed_not_oos": True, "positive_months_of_36": positive,
        "net_sum_separate_years_usd_oz": sum(r["net_usd_oz"] for r in results),
        "passes_locked_gate": passed, "years": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
