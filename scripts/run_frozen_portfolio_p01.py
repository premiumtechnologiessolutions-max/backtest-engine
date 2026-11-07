"""NRF-FAC-P01: preregistered fixed shared-capacity negative control.

Do not optimize, reorder, or replace parameters under P01 ID.
2012–2013 are historically exposed, NOT clean out-of-sample.
Original private XAUUSD ZIP never goes to GitHub/CI.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from norisk_quant.data import load_market, sha256_file, fingerprint_loaded_m1
from norisk_quant.execution import run as run_reference
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.strategies_native import donchian_breakout_signals
from norisk_quant.strategy import aggregate_bars
from scripts.batch_donchian_grid import ORIGINAL
from scripts.batch_wick_rejection_grid import (
    wick_rejection_signal_arrays, to_native_signals,
)

FROZEN = {
    "research_id": "NRF-FAC-P01",
    "years": [2012, 2013],
    "donchian": {"timeframe": "M15", "lookback": 10, "stop": 5.0, "target": 10.0},
    "wick": {"timeframe": "M15", "wick_body": 1.50, "min_range": 3.0,
             "stop": 5.0, "target": 10.0},
    "tie_priority": "wick first, Donchian second; stable timestamp sort",
    "one_shared_position": True,
    "roundtrip_all_in_usd_oz": 0.40,
    "original_source_sha256": ORIGINAL,
    "warning": "Negative control, not optimized, not OOS or live evidence",
}


def run_frozen(source: Path, out: Path) -> dict:
    if sha256_file(source) != ORIGINAL:
        raise ValueError("Private original ZIP SHA-256 mismatch")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "portfolio_summary.json").exists():
        raise FileExistsError("Refuse to overwrite an accepted P01 run")
    (out / "frozen_spec.json").write_text(json.dumps(FROZEN, indent=2))
    monthly_rows, yearly_rows, parity = [], [], []
    settings = Settings(ounces=1.0, roundtrip_cost_per_ounce=0.40)
    for year in (2012, 2013):
        m1 = load_market(source, f"{year}-01-01", f"{year}-12-31")
        d = donchian_breakout_signals(
            m1, timeframe="M15", lookback=10,
            stop_distance=5.0, target_distance=10.0,
        )
        times, sides = wick_rejection_signal_arrays(
            aggregate_bars(m1, "M15"), wick_body=1.5, min_range=3.0,
        )
        w = to_native_signals(times, sides, 5.0, 10.0)
        results = {}
        for name, signals in [
            ("wick_only", w),
            ("donchian_only", d),
            ("shared_capacity_wick_first", w + d),
        ]:
            result = run_fast(m1, signals, settings)
            monthly = np.bincount(
                pd.to_datetime(result.trades.closed_at, utc=True).dt.month,
                weights=result.trades.net_pnl.to_numpy(), minlength=13,
            )[1:]
            equity = result.equity.equity
            drawdown = float(
                (equity.cummax().clip(lower=0) - equity).clip(lower=0).max()
            )
            yearly_rows.append({
                "year": year, "variant": name, "trades": len(result.trades),
                "net_usd_oz": float(result.trades.net_pnl.sum()),
                "fees_usd": float(result.trades.cost.sum()),
                "positive_months": int((monthly > 0).sum()),
                "max_m1_floating_dd_usd_oz": drawdown,
                "signals": len(signals),
                "loaded_m1_sha256": fingerprint_loaded_m1(m1),
            })
            monthly_rows.extend([
                {"year": year, "month": i + 1, "variant": name,
                 "settled_net_usd_oz": float(net)}
                for i, net in enumerate(monthly)
            ])
            results[name] = (result, monthly)
        naive = results["wick_only"][1] + results["donchian_only"][1]
        monthly_rows.extend([
            {"year": year, "month": i + 1,
             "variant": "naive_sum_INVALID_NOT_SHARED",
             "settled_net_usd_oz": float(net)}
            for i, net in enumerate(naive)
        ])
        if np.allclose(naive, results["shared_capacity_wick_first"][1]):
            raise AssertionError("P01 expected distinct shared-capacity behavior")
        shared = results["shared_capacity_wick_first"][0]
        original = run_reference(m1, w + d, settings)
        pd.testing.assert_frame_equal(
            shared.trades.reset_index(drop=True),
            original.trades.reset_index(drop=True),
            check_exact=False, rtol=0, atol=1e-8,
        )
        np.testing.assert_allclose(
            shared.equity.equity.to_numpy(),
            original.equity.equity.to_numpy(),
            rtol=0, atol=1e-8,
        )
        parity.append({
            "year": year, "full_trade_ledger": "MATCH",
            "trades": len(shared.trades),
            "every_observed_m1_equity_mark": "MATCH",
            "observed_m1_equity_marks": len(m1),
            "max_net_delta": float(np.max(np.abs(
                shared.trades.net_pnl - original.trades.net_pnl
            ))),
        })
    pd.DataFrame(monthly_rows).to_csv(out / "portfolio_monthly.csv", index=False)
    pd.DataFrame(yearly_rows).to_csv(out / "portfolio_yearly_summary.csv", index=False)
    (out / "portfolio_reference_parity.json").write_text(json.dumps(parity, indent=2))
    summary = {
        "status": "REJECTED_NEGATIVE_CONTROL_NOT_OOS",
        "frozen": FROZEN,
        "yearly": yearly_rows,
        "reference_full_ledger_and_every_m1_equity_parity": parity,
        "warning": "Naive sum is not shared portfolio P/L",
    }
    (out / "portfolio_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-zip", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run_frozen(args.gold_zip, args.out), indent=2))


if __name__ == "__main__":
    main()
