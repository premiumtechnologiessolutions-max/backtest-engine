"""NRF-FAC-002: countertrend fade of fully closed Donchian M15 breaches.

Same native Donchian event as FAC-001, but ENTER OPPOSITE DIRECTION.
20 lookbacks * 25 stops * 40 targets = 20,000 variants per year.
Frozen before opening any FAC-002 original-data historical results.
No real broker tick-fills; design data is historically exposed.
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.batch_donchian_grid import (
    ORIGINAL, LOOKBACKS, STOPS, TARGETS, replay_core, get_signals, HAS_JIT,
)
from norisk_quant.data import sha256_file, load_market, fingerprint_loaded_m1
from norisk_quant.model import Settings
from norisk_quant.fast_engine import run_fast
from norisk_quant.strategies_native import donchian_breakout_signals

SPEC = {
    "research_id": "NRF-FAC-002",
    "hypothesis": "Fade rather than follow native M15 close-confirmed Donchian break",
    "lookbacks": list(LOOKBACKS),
    "stops_usd": list(STOPS),
    "targets_usd": list(TARGETS),
    "design_years": [2012, 2013],
    "source_sha256": ORIGINAL,
    "fee_all_in_per_oz": .40,
    "one_position": True,
    "warnings": "Parameter grid is correlated and historically exposed, not independent out-of-sample",
}


def run_batch(m1: pd.DataFrame, *, year: int, out: Path, max_candidates: int = 20000):
    if type(year) is not int or year not in (2012, 2013):
        raise ValueError("Frozen research permits years 2012 and 2013 only")
    if type(max_candidates) is not int or not 1 <= max_candidates <= 20000:
        raise ValueError("Expected 1–20000 candidate evaluations")
    if max_candidates > 100 and not HAS_JIT:
        raise RuntimeError("Optional Numba is required for full-scale research")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "search_summary.json").exists():
        raise FileExistsError("Refusing to overwrite completed research")
    (out / "frozen_spec.json").write_text(
        json.dumps(SPEC, indent=2), encoding="utf-8"
    )
    stamps = m1.index.asi8 // 1_000_000_000
    o, h, l, c = [m1[k].to_numpy(dtype=np.float64) for k in ("o", "h", "l", "c")]
    months = (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8)
    begin = time.perf_counter()
    outcomes = []
    for lookback in LOOKBACKS:
        times, sides = get_signals(m1, lookback)
        sides = -sides  # PREDECLARED reversal of the original causal event.
        for stop, target in itertools.product(STOPS, TARGETS):
            if len(outcomes) >= max_candidates:
                break
            monthly, trades, net, fees, dd, _ = replay_core(
                stamps, o, h, l, c, months, times, sides,
                float(stop), float(target),
            )
            outcomes.append((
                lookback, stop, target, trades, net, fees, dd,
                int((monthly > 0).sum()), float(monthly.min()),
                *monthly.tolist(),
            ))
        if len(outcomes) >= max_candidates:
            break
    columns = [
        "lookback", "stop_usd", "target_usd", "trades", "net_usd_oz",
        "fees_usd", "max_m1_dd", "positive_months", "worst_month",
    ] + [f"m{i:02d}" for i in range(1, 13)]
    table = pd.DataFrame(outcomes, columns=columns)
    table["id"] = [
        f"FADE15_L{int(lb):02d}_SL{stop:.2f}_TP{target:.2f}"
        for lb, stop, target in zip(
            table.lookback, table.stop_usd, table.target_usd
        )
    ]
    if not table.id.is_unique:
        raise AssertionError("Duplicate strategy specification")
    parity = []
    for sample in table.iloc[sorted(set(
        (0, len(table) // 2, len(table) - 1)
    ))].itertuples():
        native = donchian_breakout_signals(
            m1, timeframe="M15", lookback=int(sample.lookback),
            stop_distance=float(sample.stop_usd),
            target_distance=float(sample.target_usd),
        )
        fade = [
            replace(s, side=-s.side, strategy="donchian_m15_fade")
            for s in native
        ]
        original = run_fast(
            m1, fade, Settings(
                ounces=1.0, roundtrip_cost_per_ounce=0.40,
            ),
        )
        booked = np.bincount(
            pd.to_datetime(original.trades.closed_at, utc=True).dt.month,
            weights=original.trades.net_pnl.to_numpy(),
            minlength=13,
        )[1:]
        projected = np.array([
            getattr(sample, f"m{i:02d}") for i in range(1, 13)
        ], dtype=float)
        delta = float(np.max(np.abs(booked - projected)))
        equity = original.equity.equity
        ref_dd = float(
            (equity.cummax().clip(lower=0) - equity)
            .clip(lower=0).max()
        )
        if (
            delta > 1e-7
            or abs(ref_dd - sample.max_m1_dd) > 1e-7
            or len(original.trades) != sample.trades
            or abs(original.trades.net_pnl.sum() - sample.net_usd_oz) > 1e-7
            or abs(original.trades.cost.sum() - sample.fees_usd) > 1e-7
        ):
            raise AssertionError(
                f"Canonical Market parity failure: {sample.id}"
            )
        parity.append({
            "id": sample.id,
            "trades": int(sample.trades),
            "monthly_delta": delta,
            "max_drawdown_delta": abs(ref_dd - sample.max_m1_dd),
        })
    table.to_csv(out / "all_candidates_monthly.csv", index=False)
    table.sort_values(
        ["positive_months", "worst_month", "net_usd_oz"],
        ascending=[False, False, False],
    ).head(20).to_csv(
        out / "exploratory_top20_NOT_OOS.csv", index=False
    )
    summary = {
        "status": "VERIFIED_DESIGN_ONLY_NOT_OOS",
        "year": year,
        "evaluated_variants": len(table),
        "original_source_sha256": ORIGINAL,
        "loaded_m1_sha256": fingerprint_loaded_m1(m1),
        "canonical_engine_parity": parity,
        "variants_positive_year_net": int((table.net_usd_oz > 0).sum()),
        "max_positive_months": int(table.positive_months.max()),
        "variants_positive_12_months": int(
            (table.positive_months == 12).sum()
        ),
        "elapsed_seconds": round(time.perf_counter() - begin, 3),
        "warning": "Correlated historical parameter search is NOT OOS or live-trading evidence.",
    }
    (out / "search_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=20000)
    args = parser.parse_args()
    if args.year not in (2012, 2013):
        raise ValueError("Only frozen 2012–2013 years")
    if sha256_file(args.gold_zip) != ORIGINAL:
        raise ValueError("Invalid original private archive SHA-256")
    bars = load_market(
        args.gold_zip, f"{args.year}-01-01", f"{args.year}-12-31"
    )
    print(json.dumps(run_batch(
        bars, year=args.year, out=args.out,
        max_candidates=args.limit,
    ), indent=2))


if __name__ == "__main__":
    main()
