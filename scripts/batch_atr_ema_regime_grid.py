"""NRF-FAC-005: frozen H1 relative ATR expansion + M15 EMA-cross research.

Four fast EMA x four slow EMA x four ATR gates = 64 causal signal
specifications; each x20 stop x20 target = 25,600 annual variants.
Only original private 2012/2013 historical data; NOT independent OOS.
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

FAST_EMAS = (5, 8, 12, 16)
SLOW_EMAS = (26, 34, 50, 72)
REGIME_GATES = (.80, 1.00, 1.20, 1.40)
STOPS = tuple(round(1 + .5 * i, 2) for i in range(20))
TARGETS = tuple(round(1 + .5 * i, 2) for i in range(20))
ATR_LENGTH = 14
BASELINE_LENGTH = 24
MIN_H1_TRANSITIONS = 39
TOTAL_SPECS = len(FAST_EMAS) * len(SLOW_EMAS) * len(REGIME_GATES) * len(STOPS) * len(TARGETS)
SPEC = {
    "research_id": "NRF-FAC-005",
    "family": "M15 completed EMA cross gated by H1 ATR14-SMA / prior24 ATR median",
    "fast_ema": list(FAST_EMAS), "slow_ema": list(SLOW_EMAS),
    "h1_atr_ratio_gates": list(REGIME_GATES),
    "atr_length": ATR_LENGTH, "baseline_length": BASELINE_LENGTH,
    "minimum_contiguous_h1_transitions": MIN_H1_TRANSITIONS,
    "stop_usd": list(STOPS), "target_usd": list(TARGETS),
    "design_years": [2012, 2013], "original_zip_sha256": ORIGINAL,
    "one_ounce_all_in_roundtrip_fee_usd": .40,
    "no_lookahead": "M15/H1 fully closed, H1 at or before signal close, <=60m stale",
    "market": "next eligible M1 open <=60s, one position, stop-first, adverse gaps, yearly reset",
    "warning": "Correlated variants, exposed design years, no independent OOS",
}


def h1_relative_atr(h1: pd.DataFrame) -> np.ndarray:
    """Strict complete-hour ATR(14) / median(previous 24 ATR values).

    A gap invalidates the ratio until 39 consecutive valid H1 transitions.
    No current ATR enters its own baseline.
    """
    if h1.empty:
        return np.empty(0, dtype=float)
    if not isinstance(h1.index, pd.DatetimeIndex) or h1.index.tz is None:
        raise ValueError("H1 bars require timezone-aware index")
    adjacent = h1.index.to_series().diff().eq(pd.Timedelta(hours=1))
    previous_close = h1["c"].shift(1)
    true_range = pd.concat([
        h1["h"] - h1["l"],
        (h1["h"] - previous_close).abs(),
        (h1["l"] - previous_close).abs(),
    ], axis=1).max(axis=1, skipna=False).where(adjacent)
    atr = true_range.rolling(ATR_LENGTH, min_periods=ATR_LENGTH).mean()
    prior_median = atr.shift(1).rolling(
        BASELINE_LENGTH, min_periods=BASELINE_LENGTH
    ).median()
    valid_run = adjacent.rolling(
        MIN_H1_TRANSITIONS, min_periods=MIN_H1_TRANSITIONS
    ).sum().eq(MIN_H1_TRANSITIONS)
    ratio = (atr / prior_median.where(prior_median > 0)).where(valid_run)
    return ratio.to_numpy(dtype=float)


def ema_cross_arrays(m15: pd.DataFrame, fast: int, slow: int):
    """Closed M15 cross timestamps and directions, resetting EMA after gaps."""
    if type(fast) is not int or type(slow) is not int or not 1 < fast < slow:
        raise ValueError("EMA spans must be integers with 1<fast<slow")
    if m15.empty:
        return np.empty(0, np.int64), np.empty(0, np.int8)
    adjacent = m15.index.to_series().diff().eq(pd.Timedelta(minutes=15))
    segments = (~adjacent).cumsum()
    close = m15["c"].astype(float)
    ema_fast = close.groupby(segments).transform(
        lambda group: group.ewm(span=fast, adjust=False).mean()
    )
    ema_slow = close.groupby(segments).transform(
        lambda group: group.ewm(span=slow, adjust=False).mean()
    )
    # slow+2 complete bars including the crossing candle and its predecessor.
    eligible = close.groupby(segments).cumcount().ge(slow + 1)
    up = eligible & ema_fast.gt(ema_slow) & ema_fast.shift(1).le(ema_slow.shift(1))
    down = eligible & ema_fast.lt(ema_slow) & ema_fast.shift(1).ge(ema_slow.shift(1))
    if (up & down).any():
        raise AssertionError("EMA cross simultaneously both directions")
    keep = np.flatnonzero((up | down).to_numpy(dtype=bool))
    stamps = np.asarray(
        m15["close_at"].iloc[keep].array.asi8 // 1_000_000_000,
        dtype=np.int64,
    )
    sides = np.where(up.iloc[keep].to_numpy(), 1, -1).astype(np.int8)
    return stamps, sides


def gated_signals(times, sides, h1_close_times, h1_ratio, gate: float):
    """As-of latest fully closed H1 only; no forward join or stale regime."""
    if not np.isfinite(gate) or gate <= 0:
        raise ValueError("Positive finite ATR regime gate required")
    if len(times) != len(sides) or len(h1_close_times) != len(h1_ratio):
        raise ValueError("Mismatched signal/regime arrays")
    if not len(times) or not len(h1_close_times):
        return np.empty(0, np.int64), np.empty(0, np.int8)
    latest = np.searchsorted(h1_close_times, times, side="right") - 1
    safe = np.maximum(latest, 0)
    age = times - h1_close_times[safe]
    allowed = ((latest >= 0) & (age >= 0) & (age <= 3600)
               & np.isfinite(h1_ratio[safe]) & (h1_ratio[safe] >= gate))
    return times[allowed], sides[allowed]


def canonical_signals(times, sides, stop: float, target: float):
    return [
        Signal(
            confirmed_at=pd.Timestamp(int(t), unit="s", tz="UTC"),
            side=int(side), stop_distance=float(stop),
            target_distance=float(target),
            strategy="M15_EMA_cross_H1_ATR_expansion",
        )
        for t, side in zip(times, sides)
    ]


def run_batch(m1: pd.DataFrame, *, year: int, out: Path, limit: int = TOTAL_SPECS):
    if type(year) is not int or year not in (2012, 2013):
        raise ValueError("Only frozen 2012 and 2013 design years")
    if type(limit) is not int or not 1 <= limit <= TOTAL_SPECS:
        raise ValueError("Candidate limit must be 1..25600")
    if limit > 100 and not HAS_JIT:
        raise RuntimeError("Numba required for full research sweep")
    out = Path(out)
    if (out / "summary.json").exists():
        raise FileExistsError("Refuse to overwrite a completed research batch")
    out.mkdir(parents=True, exist_ok=True)
    frozen = out / "frozen_spec.json"
    if frozen.is_file() and json.loads(frozen.read_text()) != SPEC:
        raise ValueError("Conflicting frozen specification")
    frozen.write_text(json.dumps(SPEC, indent=2), encoding="utf-8")
    m15 = aggregate_bars(m1, "M15")
    h1 = aggregate_bars(m1, "H1")
    ratio = h1_relative_atr(h1)
    h1_times = np.asarray(h1["close_at"].array.asi8 // 1_000_000_000, dtype=np.int64)
    stamps = np.asarray(m1.index.asi8 // 1_000_000_000, dtype=np.int64)
    op, hi, lo, cl = (m1[k].to_numpy(dtype=float) for k in ("o", "h", "l", "c"))
    months = (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8)
    started = time.perf_counter()
    cache = {}
    signal_hashes = set()
    rows = []
    for fast, slow in itertools.product(FAST_EMAS, SLOW_EMAS):
        crossed_times, crossed_sides = ema_cross_arrays(m15, fast, slow)
        for gate in REGIME_GATES:
            times, sides = gated_signals(
                crossed_times, crossed_sides, h1_times, ratio, gate
            )
            cache[(fast, slow, gate)] = (times, sides)
            signal_hashes.add(hashlib.sha256(
                times.tobytes() + sides.tobytes()
            ).hexdigest())
            for stop, target in itertools.product(STOPS, TARGETS):
                if len(rows) >= limit:
                    break
                monthly, trades, net, fees, dd, expired = replay_core(
                    stamps, op, hi, lo, cl, months,
                    times, sides, float(stop), float(target),
                )
                ident = f"ATRH1_EMA15_F{fast:02d}_S{slow:02d}_G{gate:.2f}_SL{stop:.2f}_TP{target:.2f}"
                rows.append((
                    ident, fast, slow, gate, stop, target, len(times), expired,
                    trades, net, fees, dd, int((monthly > 0).sum()),
                    float(monthly.min()), *monthly.tolist(),
                ))
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break
    cols = [
        "id", "fast", "slow", "gate", "stop_usd", "target_usd",
        "signals", "expired", "trades", "net_usd_oz", "fees_usd",
        "max_m1_dd", "positive_months", "worst_month",
    ] + [f"m{i:02d}" for i in range(1, 13)]
    table = pd.DataFrame(rows, columns=cols)
    if not table.id.is_unique:
        raise AssertionError("Duplicate frozen candidate IDs")
    selected = sorted(set([
        0, len(table) // 5, len(table) // 3, len(table) // 2,
        len(table) * 4 // 5, len(table) - 1,
    ]))
    parity = []
    for row in table.iloc[selected].itertuples():
        times, sides = cache[(int(row.fast), int(row.slow), float(row.gate))]
        original = run_fast(
            m1, canonical_signals(times, sides, row.stop_usd, row.target_usd),
            Settings(ounces=1.0, roundtrip_cost_per_ounce=.40),
        )
        booked = np.bincount(
            pd.to_datetime(original.trades.closed_at, utc=True).dt.month,
            weights=original.trades.net_pnl.to_numpy(), minlength=13,
        )[1:]
        observed = np.array([
            getattr(row, f"m{i:02d}") for i in range(1, 13)
        ], dtype=float)
        delta = float(np.max(np.abs(booked - observed)))
        equity = original.equity.equity
        canonical_dd = float(
            (equity.cummax().clip(lower=0) - equity).clip(lower=0).max()
        )
        dd_delta = abs(canonical_dd - row.max_m1_dd)
        if (delta > 1e-7 or dd_delta > 1e-7
            or len(original.trades) != row.trades
            or abs(original.trades.net_pnl.sum() - row.net_usd_oz) > 1e-7
            or abs(original.trades.cost.sum() - row.fees_usd) > 1e-7):
            raise AssertionError(f"Original run_fast parity failed: {row.id}")
        parity.append({
            "id": row.id, "filled": int(row.trades),
            "max_month_delta": delta, "floating_dd_delta": dd_delta,
        })
    table.to_csv(out / "all_candidates_monthly.csv", index=False)
    table.sort_values(
        ["positive_months", "worst_month", "net_usd_oz"],
        ascending=[False, False, False],
    ).head(20).to_csv(out / "exploratory_top20_NOT_OOS.csv", index=False)
    summary = {
        "status": "COMPLETED_HISTORICALLY_EXPOSED_DESIGN_NOT_OOS",
        "year": year, "evaluated_parameter_specs": len(table),
        "unique_entry_signal_sequences": len(signal_hashes),
        "zero_trade_specs": int((table.trades == 0).sum()),
        "original_zip_sha256": ORIGINAL,
        "loaded_m1_sha256": fingerprint_loaded_m1(m1),
        "observed_m1_rows": len(m1),
        "complete_m15_bars": len(m15), "complete_h1_bars": len(h1),
        "positive_annual_net_specs": int((table.net_usd_oz > 0).sum()),
        "max_positive_months": int(table.positive_months.max()),
        "positive_12_months": int((table.positive_months == 12).sum()),
        "canonical_original_parity": parity,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "warning": "Historical correlated parameter search; no independent OOS or profit guarantee.",
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-zip", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=TOTAL_SPECS)
    args = parser.parse_args()
    if sha256_file(args.gold_zip) != ORIGINAL:
        raise ValueError("Refusing non-original gold archive")
    m1 = load_market(args.gold_zip, f"{args.year}-01-01", f"{args.year}-12-31")
    print(json.dumps(run_batch(m1, year=args.year, out=args.out, limit=args.limit), indent=2))


if __name__ == "__main__":
    main()
