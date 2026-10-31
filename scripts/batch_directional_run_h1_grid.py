"""NRF-FAC-011: frozen M15 directional-run + completed H1 regime + DST-aware sessions.

Preregistered BEFORE reading FAC011 outcomes at GitHub commit
4dc11184bc6118aab8e97450bc0c0c884cd23d85. 2012/2013 are
historically exposed design, NOT clean OOS. Never upload private quotes.
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
from scripts.batch_donchian_grid import ORIGINAL, HAS_JIT, replay_core
from scripts.batch_h1_range_ema_grid import h1_range_relative

RUN_LENGTHS = (2, 3, 4, 5)
MOVE_THRESHOLDS = (1.0, 1.5, 2.0, 3.0)
MODES = ("FADE", "FOLLOW")
REGIMES = ("QUIET", "HOT")
SESSIONS = ("ALL", "LONDON_LOCAL_08_12", "NY_LOCAL_0930_1330")
STOPS = (1., 2., 3., 4., 5., 6., 7., 8., 9., 10.)
TARGETS = (.5, 1., 1.5, 2., 2.5, 3., 4., 5., 6., 8.)
TOTAL = 19200
PREREG = "4dc11184bc6118aab8e97450bc0c0c884cd23d85"
SPEC = {
    "research_id": "NRF-FAC-011",
    "preregistration_commit": PREREG,
    "family": "exact M15 directional-run normalized by prior32 M15 range, H1 regime, DST-local session",
    "run_lengths": list(RUN_LENGTHS), "move_thresholds": list(MOVE_THRESHOLDS),
    "modes": list(MODES), "regimes": list(REGIMES), "sessions": list(SESSIONS),
    "stops": list(STOPS), "targets": list(TARGETS), "specs_per_year": TOTAL,
    "years": [2012, 2013], "source_sha256": ORIGINAL,
    "fee_all_in_roundtrip_usd_per_oz": .4, "design_only_not_oos": True,
}


def directional_run_signals(m15: pd.DataFrame, run_length: int, threshold: float):
    """Exactly N consecutive same-sign M15 close deltas, prior 32 range median."""
    if run_length not in RUN_LENGTHS or threshold not in MOVE_THRESHOLDS:
        raise ValueError("Non-frozen run/threshold")
    if m15.empty:
        return np.empty(0, np.int64), np.empty(0, np.int8)
    close = m15.c.to_numpy(dtype=np.float64)
    ranges = (m15.h - m15.l).to_numpy(dtype=np.float64)
    stamps = np.asarray(m15.close_at.array.asi8 // 1_000_000_000, dtype=np.int64)
    segments = np.cumsum(np.r_[True, np.diff(m15.index.asi8) != 900_000_000_000]).astype(np.int64)
    direction = np.sign(np.r_[np.nan, np.diff(close)]).astype(np.float64)
    direction[~np.isfinite(direction)] = 0.
    streak = np.zeros(len(close), dtype=np.int16)
    for i in range(1, len(close)):
        if segments[i] != segments[i-1] or direction[i] == 0:
            continue
        streak[i] = streak[i-1] + 1 if direction[i] == direction[i-1] else 1
    baseline = pd.Series(ranges).shift(1).rolling(32, min_periods=32).median().to_numpy()
    eligible = np.arange(len(close)) >= max(32, run_length)
    oldest = np.maximum(0, np.arange(len(close)) - 32)
    eligible &= segments == segments[oldest]
    eligible &= np.isfinite(baseline) & (baseline > 0)
    eligible &= streak == run_length
    idx = np.flatnonzero(eligible)
    if not len(idx):
        return np.empty(0, np.int64), np.empty(0, np.int8)
    move = np.abs(close[idx] - close[idx-run_length]) / baseline[idx]
    idx = idx[move >= threshold]
    return stamps[idx], direction[idx].astype(np.int8)


def causal_filters(m15: pd.DataFrame, h1: pd.DataFrame):
    """Join only closed H1, and evaluate true London/New York local DST time."""
    times = np.asarray(m15.close_at.array.asi8 // 1_000_000_000, dtype=np.int64)
    h1times = np.asarray(h1.close_at.array.asi8 // 1_000_000_000, dtype=np.int64)
    ratios = h1_range_relative(h1)
    regime = np.zeros(len(times), dtype=np.int8)
    if len(h1times):
        last = np.searchsorted(h1times, times, side="right") - 1
        safe = np.maximum(0, last)
        age = times - h1times[safe]
        valid = (last >= 0) & (age >= 0) & (age <= 3600) & np.isfinite(ratios[safe])
        regime[valid & (ratios[safe] <= 1.)] = 1
        regime[valid & (ratios[safe] > 1.)] = 2
    london = m15.close_at.dt.tz_convert("Europe/London")
    newyork = m15.close_at.dt.tz_convert("America/New_York")
    london_min = (london.dt.hour * 60 + london.dt.minute).to_numpy()
    ny_min = (newyork.dt.hour * 60 + newyork.dt.minute).to_numpy()
    sessions = {
        "ALL": np.ones(len(times), dtype=bool),
        "LONDON_LOCAL_08_12": (london_min >= 480) & (london_min < 720),
        "NY_LOCAL_0930_1330": (ny_min >= 570) & (ny_min < 810),
    }
    return times, regime, sessions


def filtered_signals(base_times, base_sides, m15_times, regime_array,
                     session_masks, mode, regime, session):
    if mode not in MODES or regime not in REGIMES or session not in SESSIONS:
        raise ValueError("Non-frozen filter")
    if not len(base_times):
        return np.empty(0, np.int64), np.empty(0, np.int8)
    idx = np.searchsorted(m15_times, base_times)
    if np.any(idx >= len(m15_times)) or np.any(m15_times[idx] != base_times):
        raise ValueError("Signals must be completed M15 timestamps")
    wanted = 1 if regime == "QUIET" else 2
    valid = (regime_array[idx] == wanted) & session_masks[session][idx]
    return base_times[valid], (base_sides[valid] * (1 if mode == "FOLLOW" else -1)).astype(np.int8)


def canonical_signals(times, sides, stop, target):
    return [
        Signal(pd.Timestamp(int(t), unit="s", tz="UTC"), int(side),
               float(stop), float(target), "FAC011_DIRECTIONAL_RUN")
        for t, side in zip(times, sides)
    ]


def run_batch(m1, year: int, out: Path, limit: int = TOTAL):
    if type(year) is not int or year not in (2012, 2013):
        raise ValueError("Frozen years only")
    if type(limit) is not int or not 1 <= limit <= TOTAL:
        raise ValueError("Invalid frozen limit")
    if limit > 100 and not HAS_JIT:
        raise RuntimeError("Numba required for bulk replay")
    out = Path(out)
    if (out / "summary.json").exists():
        raise FileExistsError("No overwrite of completed experiment")
    out.mkdir(parents=True, exist_ok=True)
    frozen = out / "frozen_spec.json"
    if frozen.exists() and json.loads(frozen.read_text()) != SPEC:
        raise ValueError("Conflicting frozen spec")
    frozen.write_text(json.dumps(SPEC, indent=2), encoding="utf-8")
    started = time.perf_counter()
    m15 = aggregate_bars(m1, "M15")
    h1 = aggregate_bars(m1, "H1")
    m15times, regime_array, session_masks = causal_filters(m15, h1)
    stamps = np.asarray(m1.index.asi8 // 1_000_000_000, dtype=np.int64)
    op, hi, lo, cl = (m1[k].to_numpy(dtype=float) for k in ("o", "h", "l", "c"))
    months = (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8)
    cache, hashes, rows = {}, set(), []
    for n, k in itertools.product(RUN_LENGTHS, MOVE_THRESHOLDS):
        base_t, base_s = directional_run_signals(m15, n, k)
        for mode, regime, session in itertools.product(MODES, REGIMES, SESSIONS):
            st, sd = filtered_signals(base_t, base_s, m15times, regime_array,
                                      session_masks, mode, regime, session)
            cache[(n, k, mode, regime, session)] = (st, sd)
            hashes.add(hashlib.sha256(st.tobytes() + sd.tobytes()).hexdigest())
            for stop, target in itertools.product(STOPS, TARGETS):
                if len(rows) >= limit:
                    break
                monthly, trades, net, fees, dd, expired = replay_core(
                    stamps, op, hi, lo, cl, months, st, sd, float(stop), float(target))
                ident = (f"RUN15_N{n}_K{k:.2f}_{mode}_{regime}_{session}"
                         f"_SL{stop:.2f}_TP{target:.2f}")
                rows.append((ident, n, k, mode, regime, session, stop, target,
                             len(st), expired, trades, net, fees, dd,
                             int((monthly > 0).sum()), float(monthly.min()),
                             *monthly.tolist()))
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    cols = ["id", "run_length", "move_threshold", "mode", "regime", "session",
            "stop_usd", "target_usd", "signals", "expired", "trades",
            "net_usd_oz", "fees_usd", "max_m1_dd", "positive_months",
            "worst_month"] + [f"m{i:02d}" for i in range(1, 13)]
    table = pd.DataFrame(rows, columns=cols)
    if not table.id.is_unique:
        raise AssertionError("Duplicate parameter IDs")
    if not np.allclose(table.net_usd_oz,
                       table[[f"m{i:02d}" for i in range(1, 13)]].sum(axis=1), atol=1e-7):
        raise AssertionError("Monthly reconciliation failed")
    if not np.allclose(table.fees_usd, .4 * table.trades, atol=1e-7):
        raise AssertionError("Fee reconciliation failed")
    picks = sorted(set([0, len(table)//5, len(table)//2, len(table)-1]))
    parity = []
    for row in table.iloc[picks].itertuples(index=False):
        st, sd = cache[(row.run_length, row.move_threshold, row.mode,
                        row.regime, row.session)]
        ref = run_fast(m1, canonical_signals(st, sd, row.stop_usd, row.target_usd),
                       Settings(ounces=1., roundtrip_cost_per_ounce=.4))
        booked = np.bincount(
            pd.to_datetime(ref.trades.closed_at, utc=True).dt.month,
            weights=ref.trades.net_pnl.to_numpy(), minlength=13)[1:]
        expected = np.array([getattr(row, f"m{i:02d}") for i in range(1, 13)])
        month_delta = float(np.max(np.abs(booked - expected)))
        equity = ref.equity.equity
        dd = float((equity.cummax().clip(lower=0) - equity).clip(lower=0).max())
        dd_delta = abs(dd - row.max_m1_dd)
        if (month_delta > 1e-7 or dd_delta > 1e-7 or len(ref.trades) != row.trades
                or abs(ref.trades.net_pnl.sum() - row.net_usd_oz) > 1e-7
                or abs(ref.trades.cost.sum() - row.fees_usd) > 1e-7):
            raise AssertionError(f"Reference parity failed: {row.id}")
        parity.append({"id": row.id, "trades": int(row.trades),
                       "max_month_delta": month_delta, "max_m1_dd_delta": dd_delta})
    table.to_csv(out / "all_candidates_monthly.csv", index=False)
    table.sort_values(["positive_months", "worst_month", "net_usd_oz"],
                      ascending=[False, False, False]).head(20).to_csv(
        out / "exploratory_top20_NOT_OOS.csv", index=False)
    summary = {
        "status": "LOCALLY_COMPLETED_HISTORICALLY_EXPOSED_DESIGN_NOT_OOS",
        "year": year, "executed_specs": len(table),
        "completed_monthly_points": len(table)*12,
        "unique_entry_signal_sequences": len(hashes),
        "zero_trade_specs": int((table.trades == 0).sum()),
        "positive_annual_net_specs": int((table.net_usd_oz > 0).sum()),
        "max_positive_months": int(table.positive_months.max()),
        "configs_12_of_12": int((table.positive_months == 12).sum()),
        "m1_rows": len(m1), "m15_complete": len(m15), "h1_complete": len(h1),
        "original_source_sha256": ORIGINAL,
        "loaded_m1_sha256": fingerprint_loaded_m1(m1),
        "local_reference_parity": parity,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "warning": "Exposed design; correlated variants, no OOS or broker fills.",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return table, summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gold-zip", type=Path, required=True)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--limit", type=int, default=TOTAL)
    args = p.parse_args()
    if sha256_file(args.gold_zip) != ORIGINAL:
        raise ValueError("Original private Gold ZIP SHA mismatch")
    m1 = load_market(args.gold_zip, f"{args.year}-01-01", f"{args.year}-12-31")
    print(json.dumps(run_batch(m1, args.year, args.out, args.limit)[1], indent=2))


if __name__ == "__main__":
    main()
