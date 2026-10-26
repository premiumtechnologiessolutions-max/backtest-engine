"""NRF-FAC-001: high-throughput monthly XAUUSD Donchian parameter research.

20 lookbacks * 25 stop distances * 40 target distances = exactly 20,000
distinct full-cycle Market strategy specifications PER YEAR. The native
norisk_quant strategy generates signals; a Numba event replay accelerates
only executions. Every run verifies 3 representative outcomes against the
canonical run_fast on the same ORIGINAL private M1 data.

Exploratory parameter search on exposed 2012–13. NOT independent OOS,
multi-strategy combination, broker-tick fills or a profit guarantee.
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from numba import njit
    HAS_JIT = True
except ImportError:
    HAS_JIT = False

    def njit(*args, **kwargs):
        # Permit standard pytest CI without installing optional acceleration.
        # Full searches require the JIT; only tiny fixtures use this fallback.
        return lambda function: function

from norisk_quant.data import fingerprint_loaded_m1, load_market, sha256_file
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings
from norisk_quant.strategies_native import donchian_breakout_signals

ORIGINAL = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
LOOKBACKS = tuple(range(5, 25))
STOPS = tuple(round(1 + 0.5 * k, 2) for k in range(25))
TARGETS = tuple(round(1 + 0.5 * k, 2) for k in range(40))

SPEC = {
    "research_id": "NRF-FAC-001",
    "family": "Donchian M15 close-confirmed Market breakout",
    "lookbacks": list(LOOKBACKS),
    "stops_usd": list(STOPS),
    "targets_usd": list(TARGETS),
    "design_years": [2012, 2013],
    "source_sha256": ORIGINAL,
    "roundtrip_all_in_fee_usd_oz": 0.40,
    "market_execution": "Same BID-reference OHLC, stop-first, adverse open gap-through, next available open, 1-ounce, one position",
    "warning": "Correlated in-sample grid; no independent OOS or live trading claim",
}


@njit(cache=True)
def replay_core(stamps, op, hi, lo, cl, months, signalt, signs, stopdist, targetdist):
    """Event driven equivalent of current run_fast Market replay (no time cap).

    Months are UTC exit-booked P&L; M1 floating marks include entire fee.
    Skip stale >1 minute signals, no same-minute replacement after exit.
    """
    count, signals_count = len(stamps), len(signalt)
    monthly = np.zeros(12, np.float64)
    pointer = 0
    next_free = 0
    trades = 0
    fees = realized = peak = maximum_drawdown = 0.0
    expired = 0
    while next_free < count and pointer < signals_count:
        confirmed = signalt[pointer]
        at = np.searchsorted(stamps, confirmed)
        if at < next_free:
            at = next_free
        if at >= count:
            break
        if stamps[at] - confirmed > 60:
            pointer += 1
            expired += 1
            continue
        direction = signs[pointer]
        pointer += 1
        price = op[at]
        stop = price - direction * stopdist
        target = price + direction * targetdist
        entry = at
        exited = False
        while at < count:
            opening = op[at]
            high = hi[at]
            low = lo[at]
            if at > entry:
                if (direction == 1 and opening <= stop) or (direction == -1 and opening >= stop):
                    exit_price, exited = opening, True
                elif (direction == 1 and opening >= target) or (direction == -1 and opening <= target):
                    exit_price, exited = target, True
            if not exited:
                stop_hit = low <= stop if direction == 1 else high >= stop
                target_hit = high >= target if direction == 1 else low <= target
                if stop_hit:
                    exit_price, exited = stop, True
                elif target_hit:
                    exit_price, exited = target, True
            if exited:
                outcome = direction * (exit_price - price) - 0.4
                realized += outcome
                monthly[months[at]] += outcome
                trades += 1
                fees += 0.4
                if realized > peak:
                    peak = realized
                drawdown = peak - realized
                if drawdown > maximum_drawdown:
                    maximum_drawdown = drawdown
                next_free = at + 1
                break
            marked_equity = realized + direction * (cl[at] - price) - 0.4
            if marked_equity > peak:
                peak = marked_equity
            drawdown = peak - marked_equity
            if drawdown > maximum_drawdown:
                maximum_drawdown = drawdown
            at += 1
        if not exited:
            last = count - 1
            outcome = direction * (cl[last] - price) - 0.4
            realized += outcome
            monthly[months[last]] += outcome
            trades += 1
            fees += 0.4
            if realized > peak:
                peak = realized
            drawdown = peak - realized
            if drawdown > maximum_drawdown:
                maximum_drawdown = drawdown
            next_free = count
    return monthly, trades, realized, fees, maximum_drawdown, expired


def get_signals(m1: pd.DataFrame, lookback: int):
    signals = donchian_breakout_signals(
        m1, timeframe="M15", lookback=lookback,
        stop_distance=1.0, target_distance=1.0,
    )
    times = np.asarray([
        int(pd.Timestamp(s.confirmed_at).timestamp()) for s in signals
    ], dtype=np.int64)
    sides = np.asarray([s.side for s in signals], dtype=np.int8)
    return times, sides


def run_batch(m1: pd.DataFrame, *, year: int, out: Path, max_candidates: int = 20000):
    if type(year) is not int or year not in (2012, 2013):
        raise ValueError("Frozen design years are 2012 and 2013")
    if type(max_candidates) is not int or not 1 <= max_candidates <= 20000:
        raise ValueError("Select 1..20000 distinct specifications")
    if max_candidates > 100 and not HAS_JIT:
        raise RuntimeError("Install optional numba for bulk replay (>100 variants)")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    if (out / "search_summary.json").exists():
        raise FileExistsError("Refuse to overwrite an accepted research run")
    frozen_path = out / "frozen_spec.json"
    if frozen_path.exists() and json.loads(frozen_path.read_text()) != SPEC:
        raise ValueError("Frozen research spec differs from existing run")
    frozen_path.write_text(json.dumps(SPEC, indent=2), encoding="utf-8")
    stamps = m1.index.asi8 // 1_000_000_000
    op, hi, lo, cl = [m1[k].to_numpy(dtype=np.float64) for k in ("o", "h", "l", "c")]
    months = (m1.index.month.to_numpy(dtype=np.int16) - 1).astype(np.int8)
    rows = []
    t0 = time.perf_counter()
    for lookback in LOOKBACKS:
        times, sides = get_signals(m1, lookback)
        for stop, target in itertools.product(STOPS, TARGETS):
            if len(rows) >= max_candidates:
                break
            monthly, n, net, fees, dd, expired = replay_core(
                stamps, op, hi, lo, cl, months, times, sides,
                float(stop), float(target),
            )
            rows.append((
                lookback, stop, target, n, net, fees, dd,
                int((monthly > 0).sum()), float(monthly.min()),
                *monthly.tolist(),
            ))
        if len(rows) >= max_candidates:
            break
    columns = [
        "lookback", "stop_usd", "target_usd", "trades", "net_usd_oz",
        "fees_usd", "max_m1_dd", "positive_months", "worst_month",
    ] + [f"m{m:02d}" for m in range(1, 13)]
    result = pd.DataFrame(rows, columns=columns)
    result["id"] = [
        f"DON15_L{int(lb):02d}_SL{sl:.2f}_TP{tp:.2f}"
        for lb, sl, tp in zip(result.lookback, result.stop_usd, result.target_usd)
    ]
    if not result.id.is_unique:
        raise AssertionError("Duplicate strategy specification")
    parity = []
    picks = result.iloc[sorted(set((0, len(result) // 2, len(result) - 1)))]
    for row in picks.itertuples():
        signals = donchian_breakout_signals(
            m1, timeframe="M15", lookback=int(row.lookback),
            stop_distance=float(row.stop_usd),
            target_distance=float(row.target_usd),
        )
        original = run_fast(
            m1, signals, Settings(ounces=1.0, roundtrip_cost_per_ounce=0.40)
        )
        booked = np.bincount(
            pd.to_datetime(original.trades.closed_at, utc=True).dt.month,
            weights=original.trades.net_pnl.to_numpy(), minlength=13,
        )[1:]
        projected = np.array([
            getattr(row, f"m{month:02d}") for month in range(1, 13)
        ], dtype=float)
        delta = float(np.max(np.abs(booked - projected)))
        equity = original.equity.equity
        ref_dd = float((equity.cummax().clip(lower=0) - equity).clip(lower=0).max())
        dd_delta = abs(ref_dd - row.max_m1_dd)
        if (
            delta > 1e-7 or dd_delta > 1e-7
            or abs(original.trades.net_pnl.sum() - row.net_usd_oz) > 1e-7
            or len(original.trades) != row.trades
            or abs(original.trades.cost.sum() - row.fees_usd) > 1e-7
        ):
            raise AssertionError(f"Bulk replay/reference parity mismatch: {row.id}")
        parity.append({
            "id": row.id, "trades": int(row.trades),
            "max_month_net_delta": delta, "max_drawdown_delta": dd_delta,
        })
    result.to_csv(out / "all_candidates_monthly.csv", index=False)
    result.sort_values(
        ["positive_months", "worst_month", "net_usd_oz"],
        ascending=[False, False, False],
    ).head(20).to_csv(out / "exploratory_top20_NOT_OOS.csv", index=False)
    summary = {
        "status": "VERIFIED_DESIGN_ONLY_NOT_OOS",
        "year": year, "candidate_count": len(result),
        "family": SPEC["family"], "original_zip_sha256": ORIGINAL,
        "loaded_m1_sha256": fingerprint_loaded_m1(m1),
        "reference_fast_parity": parity,
        "months_evaluated": len(result) * 12,
        "positive_net_variants": int((result.net_usd_oz > 0).sum()),
        "maximum_positive_months": int(result.positive_months.max()),
        "variants_positive_12_of_12": int((result.positive_months == 12).sum()),
        "seconds_including_parity": round(time.perf_counter() - t0, 3),
        "warning": "Thousands of correlated historical variants are not independent strategies or evidence of future profitability.",
    }
    (out / "search_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-zip", required=True, type=Path)
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=20000)
    args = parser.parse_args()
    if args.year not in (2012, 2013):
        raise ValueError("Only frozen design years 2012 and 2013")
    if sha256_file(args.gold_zip) != ORIGINAL:
        raise ValueError("Private original market source SHA-256 mismatch")
    bars = load_market(
        args.gold_zip, f"{args.year}-01-01", f"{args.year}-12-31"
    )
    print(json.dumps(run_batch(
        bars, year=args.year, out=args.out, max_candidates=args.limit
    ), indent=2))


if __name__ == "__main__":
    main()
