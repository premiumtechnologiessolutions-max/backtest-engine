"""NRF-FAC-004: preregistered Wilder RSI M15 threshold-recross search.

64 distinct causal signal rules x 400 stops/targets = 25,600 yearly
parameter specs, 2012 and 2013 design years. Numba batch reproduces
canonical run_fast Market execution on checked samples. Historical,
correlated, NOT clean OOS; never publish original private market quotes.
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

from norisk_quant.data import sha256_file, load_market, fingerprint_loaded_m1
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings, Signal
from norisk_quant.strategy import aggregate_bars
from scripts.batch_donchian_grid import HAS_JIT, ORIGINAL, replay_core

PERIODS = (5, 7, 9, 11, 14, 18, 21, 28)
THRESHOLDS = (15, 20, 25, 30, 35, 40, 42, 45)
STOPS = tuple(round(1 + .5 * k, 2) for k in range(20))
TARGETS = tuple(round(1 + .5 * k, 2) for k in range(20))
TOTAL_SPECS = len(PERIODS) * len(THRESHOLDS) * len(STOPS) * len(TARGETS)
SPEC = {
    "research_id": "NRF-FAC-004",
    "family": "completed M15 Wilder RSI upward oversold / downward overbought recross",
    "periods": list(PERIODS),
    "thresholds": list(THRESHOLDS),
    "stops_usd": list(STOPS), "targets_usd": list(TARGETS),
    "years": [2012, 2013],
    "original_source_sha256": ORIGINAL,
    "signal_confirmation": "complete M15 close; contiguous period+1 complete bars",
    "execution": "one ounce; one position; stop-first and adverse opening gap; max signal age 60s",
    "one_all_in_roundtrip_fee_per_ounce": .40,
    "warning": "2012-13 historically exposed; these are correlated specifications, not independent OOS",
}


def rsi_recross_arrays(bars: pd.DataFrame, period: int, threshold: int):
    """Return causal [UTC seconds at close, side] arrays, never future prices."""
    if type(period) is not int or period < 2 or type(threshold) is not int or not 0 < threshold < 50:
        raise ValueError("Invalid RSI period or lower threshold")
    if bars.empty:
        return np.empty(0, np.int64), np.empty(0, np.int8)
    close = bars["c"].astype(float)
    delta = close.diff()
    avg_gain = delta.clip(lower=0).ewm(
        alpha=1/period, adjust=False, min_periods=period
    ).mean()
    avg_loss = (-delta.clip(upper=0)).ewm(
        alpha=1/period, adjust=False, min_periods=period
    ).mean()
    both = avg_gain + avg_loss
    rsi = (100 * avg_gain / both).where(both > 0, 50.)
    rsi = rsi.where(avg_gain.notna() & avg_loss.notna())
    prior = rsi.shift(1)
    spacing = bars.index.to_series().diff().eq(pd.Timedelta(minutes=15))
    contiguous = spacing.rolling(
        period + 1, min_periods=period + 1
    ).sum().eq(period + 1)
    longs = contiguous & prior.le(threshold) & rsi.gt(threshold)
    shorts = contiguous & prior.ge(100 - threshold) & rsi.lt(100 - threshold)
    if (longs & shorts).any():
        raise AssertionError("Both RSI directions simultaneously qualified")
    keep = np.flatnonzero((longs | shorts).to_numpy(dtype=bool))
    timestamps = np.asarray(
        bars["close_at"].iloc[keep].array.asi8 // 1_000_000_000,
        dtype=np.int64,
    )
    sides = np.where(longs.iloc[keep].to_numpy(), 1, -1).astype(np.int8)
    return timestamps, sides


def canonical_signals(times, sides, stop: float, target: float):
    return [
        Signal(confirmed_at=pd.Timestamp(int(t), unit="s", tz="UTC"),
               side=int(side), stop_distance=float(stop),
               target_distance=float(target),
               strategy="M15_Wilder_RSI_recross")
        for t, side in zip(times, sides)
    ]


def run_batch(m1: pd.DataFrame, *, year: int, out: Path, limit: int = TOTAL_SPECS):
    if type(year) is not int or year not in (2012, 2013):
        raise ValueError("Frozen 2012 and 2013 design years only")
    if type(limit) is not int or not 1 <= limit <= TOTAL_SPECS:
        raise ValueError("Candidate limit must be in 1..25600")
    if limit > 100 and not HAS_JIT:
        raise RuntimeError("Install numba for large-scale research")
    out = Path(out)
    if (out / "summary.json").exists():
        raise FileExistsError("Refuse to overwrite completed scientific results")
    out.mkdir(parents=True, exist_ok=True)
    frozen = out / "frozen_spec.json"
    if frozen.is_file() and json.loads(frozen.read_text()) != SPEC:
        raise ValueError("Existing experiment has another frozen specification")
    frozen.write_text(json.dumps(SPEC, indent=2), encoding="utf-8")
    bars = aggregate_bars(m1, "M15")
    stamp = np.asarray(m1.index.asi8 // 1_000_000_000, dtype=np.int64)
    op, hi, lo, cl = (m1[k].to_numpy(dtype=float) for k in ("o", "h", "l", "c"))
    months = (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8)
    started = time.perf_counter()
    cache = {}
    identities = set()
    rows = []
    signal_hashes = set()
    for period, threshold in itertools.product(PERIODS, THRESHOLDS):
        t, side = rsi_recross_arrays(bars, period, threshold)
        cache[(period, threshold)] = (t, side)
        signal_hashes.add(hashlib.sha256(t.tobytes() + side.tobytes()).hexdigest())
        for stop, target in itertools.product(STOPS, TARGETS):
            if len(rows) >= limit:
                break
            monthly, filled, net, fees, dd, expired = replay_core(
                stamp, op, hi, lo, cl, months, t, side,
                float(stop), float(target),
            )
            ident = f"RSI15_P{period:02d}_L{threshold:02d}_SL{stop:.2f}_TP{target:.2f}"
            if ident in identities:
                raise AssertionError("Duplicate strategy ID")
            identities.add(ident)
            rows.append((
                ident, period, threshold, stop, target, len(t), expired,
                filled, net, fees, dd, int((monthly > 0).sum()),
                float(monthly.min()), *monthly.tolist(),
            ))
        if len(rows) >= limit:
            break
    cols = ["id", "period", "threshold", "stop_usd", "target_usd",
            "signals", "expired", "trades", "net_usd_oz", "fees_usd",
            "max_m1_dd", "positive_months", "worst_month"] + [
        f"m{i:02d}" for i in range(1, 13)
    ]
    table = pd.DataFrame(rows, columns=cols)
    selection = sorted(set([0, len(table) // 5, len(table) // 3,
                            len(table) // 2, 4 * len(table) // 5,
                            len(table) - 1]))
    parity = []
    for row in table.iloc[selection].itertuples():
        times, sides = cache[(int(row.period), int(row.threshold))]
        original = run_fast(
            m1, canonical_signals(times, sides, row.stop_usd, row.target_usd),
            Settings(ounces=1.0, roundtrip_cost_per_ounce=.40),
        )
        booked = np.bincount(
            pd.to_datetime(original.trades.closed_at, utc=True).dt.month,
            weights=original.trades.net_pnl.to_numpy(), minlength=13,
        )[1:]
        tested_months = np.array([
            getattr(row, f"m{i:02d}") for i in range(1, 13)
        ], dtype=float)
        delta = float(np.max(np.abs(booked - tested_months)))
        floating = original.equity.equity
        dd_original = float(
            (floating.cummax().clip(lower=0) - floating).clip(lower=0).max()
        )
        if (delta > 1e-7 or abs(dd_original - row.max_m1_dd) > 1e-7
            or len(original.trades) != row.trades
            or abs(original.trades.net_pnl.sum() - row.net_usd_oz) > 1e-7
            or abs(original.trades.cost.sum() - row.fees_usd) > 1e-7):
            raise AssertionError(f"Canonical run_fast parity mismatch {row.id}")
        parity.append({"id": row.id, "filled": int(row.trades),
                       "max_month_delta": delta,
                       "floating_dd_delta": abs(dd_original - row.max_m1_dd)})
    table.to_csv(out / "all_candidates_monthly.csv", index=False)
    table.sort_values(
        ["positive_months", "worst_month", "net_usd_oz"],
        ascending=[False, False, False],
    ).head(20).to_csv(out / "exploratory_top20_NOT_OOS.csv", index=False)
    summary = {
        "status": "COMPLETED_HISTORICALLY_EXPOSED_DESIGN_NOT_OOS",
        "year": year, "evaluated_parameter_specs": len(table),
        "distinct_signal_sets": len(signal_hashes),
        "zero_trade_specs": int((table.trades == 0).sum()),
        "original_zip_sha256": ORIGINAL,
        "loaded_m1_sha256": fingerprint_loaded_m1(m1),
        "observed_m1_rows": len(m1),
        "complete_m15_bars": len(bars),
        "positive_net_variants": int((table.net_usd_oz > 0).sum()),
        "max_positive_months": int(table.positive_months.max()),
        "positive_12_months": int((table.positive_months == 12).sum()),
        "parity_checked": parity,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "warning": "Correlated backtest optimizations cannot establish independent monthly profitability.",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("--gold-zip", type=Path, required=True)
    arg.add_argument("--year", type=int, required=True)
    arg.add_argument("--out", type=Path, required=True)
    arg.add_argument("--limit", type=int, default=TOTAL_SPECS)
    opts = arg.parse_args()
    if sha256_file(opts.gold_zip) != ORIGINAL:
        raise ValueError("Refusing unverified gold archive")
    m1 = load_market(opts.gold_zip, f"{opts.year}-01-01", f"{opts.year}-12-31")
    print(json.dumps(run_batch(m1, year=opts.year, out=opts.out, limit=opts.limit), indent=2))


if __name__ == "__main__":
    main()
