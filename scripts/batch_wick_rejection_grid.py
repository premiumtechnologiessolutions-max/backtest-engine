"""NRF-FAC-003: frozen 28,800/year fully closed M15 rejection-wick variants.

12 wick/body ratios * 6 min ranges * 20 stops * 20 targets.
This is ONE correlated family, not 28,800 independent strategies.
2012/2013 are historically exposed design years, NOT clean OOS.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd

from norisk_quant.data import fingerprint_loaded_m1, load_market, sha256_file
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings, Signal
from norisk_quant.strategy import aggregate_bars
from scripts.batch_donchian_grid import HAS_JIT, ORIGINAL, replay_core

WICK_BODY = tuple(round(0.5 + 0.25 * k, 2) for k in range(12))
MIN_RANGE = (0.75, 1.5, 2.25, 3.0, 3.75, 4.5)
STOPS = tuple(round(1 + 0.5 * k, 2) for k in range(20))
TARGETS = tuple(round(1 + 0.5 * k, 2) for k in range(20))
DOMINANCE = 1.5
CLOSE_LOCATION = 0.65
MIN_BODY_DENOM = 0.10

SPEC = {
    "research_id": "NRF-FAC-003",
    "family": "fully closed M15 rejection-wick reversal",
    "wick_body_ratios": list(WICK_BODY),
    "min_range_usd": list(MIN_RANGE),
    "stop_usd": list(STOPS),
    "target_usd": list(TARGETS),
    "dominance_ratio": DOMINANCE,
    "strong_close_fraction": CLOSE_LOCATION,
    "min_body_denominator_usd": MIN_BODY_DENOM,
    "design_years": [2012, 2013],
    "original_zip_sha256": ORIGINAL,
    "all_in_roundtrip_cost_usd_oz": 0.40,
    "no_lookahead": "signal only at close_at of a fully observed M15 candle",
    "execution": "one ounce, one position, next eligible M1 open <=1m, stop-first, adverse gap-through, year-end close",
    "warning": "correlated in-sample historical search, not independent OOS or live proof",
}


def wick_rejection_signal_arrays(bars: pd.DataFrame, *, wick_body: float, min_range: float):
    """Close-confirmed price action, no future observations or fabricated M15."""
    if wick_body <= 0 or min_range <= 0:
        raise ValueError("Ratios and ranges must be positive")
    if bars.empty:
        return np.empty(0, np.int64), np.empty(0, np.int8)
    o, h, l, c = (bars[k].to_numpy(dtype=np.float64) for k in ("o", "h", "l", "c"))
    span = h - l
    body = np.maximum(np.abs(c - o), MIN_BODY_DENOM)
    lower = np.minimum(o, c) - l
    upper = h - np.maximum(o, c)
    eligible = span >= min_range
    long = eligible & (lower >= wick_body * body) & (lower >= DOMINANCE * upper) & (
        c - l >= CLOSE_LOCATION * span
    )
    short = eligible & (upper >= wick_body * body) & (upper >= DOMINANCE * lower) & (
        h - c >= CLOSE_LOCATION * span
    )
    if np.any(long & short):
        raise AssertionError("Ambiguous simultaneous rejection directions")
    positions = np.flatnonzero(long | short)
    stamps = bars["close_at"].iloc[positions].array.asi8 // 1_000_000_000
    directions = np.where(long[positions], 1, -1).astype(np.int8)
    return np.asarray(stamps, dtype=np.int64), directions


def to_native_signals(times: np.ndarray, sides: np.ndarray, stop: float, target: float):
    return [
        Signal(
            confirmed_at=pd.Timestamp(int(at), unit="s", tz="UTC"),
            side=int(side), stop_distance=float(stop), target_distance=float(target),
            strategy="m15_wick_rejection_v1",
        )
        for at, side in zip(times, sides)
    ]


def run_batch(m1: pd.DataFrame, *, year: int, out: Path, max_candidates: int = 28800):
    if type(year) is not int or year not in (2012, 2013):
        raise ValueError("Frozen research years: 2012, 2013")
    if type(max_candidates) is not int or not 1 <= max_candidates <= 28800:
        raise ValueError("Expected 1..28800 specifications")
    if max_candidates > 100 and not HAS_JIT:
        raise RuntimeError("Numba optional acceleration required for full sweep")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "search_summary.json").exists():
        raise FileExistsError("Refuse to overwrite a completed research run")
    spec_file = out / "frozen_spec.json"
    if spec_file.exists() and json.loads(spec_file.read_text()) != SPEC:
        raise ValueError("Conflicting frozen specification")
    spec_file.write_text(json.dumps(SPEC, indent=2), encoding="utf-8")
    bars = aggregate_bars(m1, "M15")
    stamps = m1.index.asi8 // 1_000_000_000
    o, h, l, c = [m1[k].to_numpy(dtype=np.float64) for k in ("o", "h", "l", "c")]
    months = (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8)
    started = time.perf_counter()
    rows = []
    sig_cache = {}
    hashes = set()
    for ratio, minrange in itertools.product(WICK_BODY, MIN_RANGE):
        signal_t, signal_s = wick_rejection_signal_arrays(
            bars, wick_body=ratio, min_range=minrange
        )
        sig_cache[(ratio, minrange)] = (signal_t, signal_s)
        hashes.add(hashlib.sha256(
            signal_t.tobytes() + signal_s.tobytes()
        ).hexdigest())
        for stop, target in itertools.product(STOPS, TARGETS):
            if len(rows) >= max_candidates:
                break
            monthly, n, net, fees, dd, expired = replay_core(
                stamps, o, h, l, c, months, signal_t, signal_s,
                float(stop), float(target),
            )
            rows.append((
                ratio, minrange, stop, target, len(signal_t), expired,
                n, net, fees, dd, int((monthly > 0).sum()),
                float(monthly.min()), *monthly.tolist(),
            ))
        if len(rows) >= max_candidates:
            break
    columns = [
        "wick_body", "min_range", "stop_usd", "target_usd", "signals", "expired_signals",
        "trades", "net_usd_oz", "fees_usd", "max_m1_dd", "positive_months",
        "worst_month",
    ] + [f"m{i:02d}" for i in range(1, 13)]
    result = pd.DataFrame(rows, columns=columns)
    result["id"] = [
        f"WICK15_W{w:.2f}_R{r:.2f}_SL{s:.2f}_TP{t:.2f}"
        for w, r, s, t in zip(
            result.wick_body, result.min_range, result.stop_usd, result.target_usd
        )
    ]
    if not result.id.is_unique:
        raise AssertionError("Duplicate parameter specification")
    picks = sorted(set([0, len(result) // 5, len(result) // 3,
                        len(result) // 2, len(result) * 4 // 5, len(result) - 1]))
    parity = []
    for row in result.iloc[picks].itertuples():
        times, sides = sig_cache[(float(row.wick_body), float(row.min_range))]
        original = run_fast(
            m1, to_native_signals(times, sides, row.stop_usd, row.target_usd),
            Settings(ounces=1.0, roundtrip_cost_per_ounce=0.40),
        )
        booked = np.bincount(
            pd.to_datetime(original.trades.closed_at, utc=True).dt.month,
            weights=original.trades.net_pnl.to_numpy(), minlength=13,
        )[1:]
        projected = np.array([getattr(row, f"m{i:02d}") for i in range(1, 13)])
        monthly_delta = float(np.max(np.abs(booked - projected)))
        equity = original.equity.equity
        reference_dd = float(
            (equity.cummax().clip(lower=0) - equity).clip(lower=0).max()
        )
        dd_delta = abs(reference_dd - row.max_m1_dd)
        if (
            monthly_delta > 1e-7 or dd_delta > 1e-7
            or len(original.trades) != row.trades
            or abs(original.trades.net_pnl.sum() - row.net_usd_oz) > 1e-7
            or abs(original.trades.cost.sum() - row.fees_usd) > 1e-7
        ):
            raise AssertionError(f"Reference parity failure {row.id}")
        parity.append({"id": row.id, "trades": int(row.trades),
                       "monthly_delta": monthly_delta, "drawdown_delta": dd_delta})
    result.to_csv(out / "all_candidates_monthly.csv", index=False)
    result[result.trades > 0].sort_values(
        ["positive_months", "worst_month", "net_usd_oz"],
        ascending=[False, False, False],
    ).head(20).to_csv(out / "exploratory_top20_NOT_OOS.csv", index=False)
    summary = {
        "status": "HISTORICALLY_EXPOSED_EXPLORATION_NOT_OOS",
        "year": year,
        "evaluated_parameter_specs": len(result),
        "zero_trade_specs": int((result.trades == 0).sum()),
        "unique_entry_signal_sequences_in_72_filters": len(hashes),
        "original_zip_sha256": ORIGINAL,
        "loaded_m1_sha256": fingerprint_loaded_m1(m1),
        "observed_m1_bars": len(m1),
        "complete_m15_bars": len(bars),
        "months_with_market_observations": int(m1.index.month.nunique()),
        "positive_annual_net_specs": int(((result.net_usd_oz > 0) & (result.trades > 0)).sum()),
        "maximum_positive_months": int(result.positive_months.max()),
        "positive_12_of_12": int((result.positive_months == 12).sum()),
        "canonical_reference_parity": parity,
        "seconds_including_parity": round(time.perf_counter() - started, 3),
        "warning": "Correlated, exposed historical variants; NOT 28800 independent strategies or future profitability",
    }
    (out / "search_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-zip", required=True, type=Path)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=28800)
    args = parser.parse_args()
    if args.year not in (2012, 2013):
        raise ValueError("Frozen design years only")
    if sha256_file(args.gold_zip) != ORIGINAL:
        raise ValueError("Original ZIP SHA256 mismatch")
    m1 = load_market(args.gold_zip, f"{args.year}-01-01", f"{args.year}-12-31")
    print(json.dumps(run_batch(m1, year=args.year, out=args.out,
                               max_candidates=args.limit), indent=2))


if __name__ == "__main__":
    main()
