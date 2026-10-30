"""FAC027 preregistered London-to-NY Asian-range continuation, research-only.

Original Gold ZIP stays local. BID-reference M1 simulation is not broker execution.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
FEE = 0.40
GRID = tuple(itertools.product((0.05, 0.15), (0.30, 0.50), (0.8, 1.2), (1.0, 1.5)))
NY = "America/New_York"


def read_year(archive, year):
    data = pd.DataFrame(json.loads(archive.read(f"{year}.json")))
    required = ("ts", "o", "h", "l", "c", "ao", "ah", "al", "ac")
    if data.empty or any(x not in data for x in required):
        raise ValueError("missing source columns")
    if not pd.api.types.is_integer_dtype(data.ts):
        raise ValueError("noninteger M1 UTC epochs")
    t = data.ts.to_numpy(dtype=np.int64)
    if np.any(t % 60) or np.any(np.diff(t) <= 0):
        raise ValueError("invalid observed UTC minute chronology")
    for c in required[1:]:
        if not np.isfinite(data[c]).all() or not (data[c] > 0).all():
            raise ValueError("invalid quote")
    if not ((data.l <= data[["o", "c"]].min(axis=1)).all()
            and (data[["o", "c"]].max(axis=1) <= data.h).all()
            and (data.al <= data[["ao", "ac"]].min(axis=1)).all()
            and (data[["ao", "ac"]].max(axis=1) <= data.ah).all()
            and (data[["ao", "ah", "al", "ac"]].ge(data[["o", "h", "l", "c"]].to_numpy()).all().all())):
        raise ValueError("invalid BID/ASK source OHLC")
    utc = pd.to_datetime(data.ts, unit="s", utc=True)
    if not (utc.dt.year == year).all() or set(utc.dt.month) != set(range(1, 13)):
        raise ValueError("invalid source calendar")
    data.index = pd.DatetimeIndex(utc)
    return data


def signal_days(data):
    """All features are known by 08:00 NY; no future M1 inspected for signal."""
    local = data.index.tz_convert(NY)
    dates = np.asarray(local.date)
    out = []
    for day, idx in pd.Series(np.arange(len(data))).groupby(dates, sort=True):
        if day.weekday() >= 5:
            continue
        indices = idx.to_numpy(dtype=np.int64)
        hours = np.asarray(local[indices].hour)
        mins = np.asarray(local[indices].minute)
        early = indices[hours < 8]
        if len(early) != 480:
            continue
        epochs = data.ts.to_numpy(dtype=np.int64)[early]
        if np.any(np.diff(epochs) != 60):
            continue
        first = local[early[0]]
        last = local[early[-1]]
        if (first.hour, first.minute, last.hour, last.minute) != (0, 0, 7, 59):
            continue
        asian, london = data.iloc[early[:180]], data.iloc[early[180:]]
        a_high, a_low = float(asian.h.max()), float(asian.l.min())
        a_range = a_high - a_low
        l_open, l_close = float(london.o.iloc[0]), float(london.c.iloc[-1])
        l_high, l_low = float(london.h.max()), float(london.l.min())
        if a_range <= 0 or l_high <= l_low:
            continue
        # Exactly five completed 60-minute London candles.
        h1 = london.groupby(np.arange(300) // 60).agg(high=("h", "max"), low=("l", "min"))
        risk = float((h1.high - h1.low).median())
        if risk <= 0 or risk / l_close > 0.003:
            continue
        efficiency = abs(l_close - l_open) / (l_high - l_low)
        if not math.isfinite(efficiency):
            continue
        # Later entry and exit quotes are inspected only during execution.
        out.append((day, indices, a_high, a_low, a_range,
                    l_open, l_close, efficiency, risk))
    return out


def execute(day_rows, data, config):
    buffer, min_efficiency, stop_mult, target_mult = config
    day, indices, ah, al, arange, lo, lc, eff, risk = day_rows
    if eff < min_efficiency:
        return None
    side = 1 if lc > ah + buffer * arange and lc > lo else (-1 if lc < al - buffer * arange and lc < lo else 0)
    if not side:
        return None
    local = data.index[indices].tz_convert(NY)
    # Exact observed 08:01 open; a later bar is not an eligible entry.
    entries = indices[(local.hour == 8) & (local.minute == 1)]
    if len(entries) != 1:
        return None
    entry_i = int(entries[0]); entry = float(data.o.iloc[entry_i])
    stop = entry - side * stop_mult * risk
    target = entry + side * target_mult * risk
    if stop <= 0 or target <= 0:
        return None
    # Never pre-filter a trade using future exit-bar availability (lookahead).
    # Discover time exits only as the actual M1 stream advances.
    session_indices = indices[indices >= entry_i]
    session_local = data.index[session_indices].tz_convert(NY)
    session_indices = session_indices[(session_local.hour < 12)
                                      | ((session_local.hour == 12) & (session_local.minute == 0))]
    peak = 0.0; dd = 0.0; marks = []
    for i in session_indices:
        bar = data.iloc[i]
        opening = float(bar.o)
        local_bar = data.index[i].tz_convert(NY)
        if local_bar.hour >= 11:
            # Favorable time-exit gap cannot claim more than frozen TP.
            if side * (opening - target) >= 0:
                price, reason = target, "target_at_time_open"
            else:
                price, reason = opening, "time"
        elif side == 1:
            if opening <= stop: price, reason = opening, "adverse_gap_stop"
            elif opening >= target: price, reason = target, "target"
            elif bar.l <= stop: price, reason = stop, "stop_first"
            elif bar.h >= target: price, reason = target, "target"
            else: price, reason = None, None
        else:
            if opening >= stop: price, reason = opening, "adverse_gap_stop"
            elif opening <= target: price, reason = target, "target"
            elif bar.h >= stop: price, reason = stop, "stop_first"
            elif bar.l <= target: price, reason = target, "target"
            else: price, reason = None, None
        if price is not None:
            net = side * (price - entry) - FEE
            marks.append((data.index[i], net))
            return {"entry_at": data.index[entry_i], "exit_at": data.index[i],
                    "net": net, "reason": reason, "marks": marks}
        # Observed M1 close mark with the full expected roundtrip fee.
        equity = side * (float(bar.c) - entry) - FEE
        marks.append((data.index[i], equity))
        peak = max(peak, equity)
        dd = max(dd, peak - equity)
    raise ValueError("missing observed time exit by 12:00 NY; incomplete source")


def simulate(data, config, *, days=None):
    if days is None:
        days = signal_days(data)
    trades = []
    monthly = defaultdict(float)
    months = [f"{data.index[0].year}-{m:02d}" for m in range(1, 13)]
    last_exit = pd.Timestamp.min.tz_localize("UTC")
    choices = (config,) if (len(config) == 4 and all(type(x) in (int, float) for x in config)) else tuple(config)
    for rows in days:
        trade = None
        for candidate in choices:  # frozen GRID order; one actual slot, no P/L summing
            trade = execute(rows, data, candidate)
            if trade is not None:
                break
        if trade is None:
            continue
        if trade["entry_at"] <= last_exit:
            continue  # one shared-capacity position per configuration
        last_exit = trade["exit_at"]
        trades.append(trade)
        monthly[trade["exit_at"].strftime("%Y-%m")] += trade["net"]
    # Equity is flat between trades; compute actual observed close-equity peaks.
    realized = 0.0; peak = 0.0; annual_dd = 0.0
    monthly_dd = {m: 0.0 for m in months}
    monthly_peaks = {}
    for trade in trades:
        for t, floating in trade["marks"]:
            equity = realized + floating
            peak = max(peak, equity)
            annual_dd = max(annual_dd, peak - equity)
            month = t.strftime("%Y-%m")
            monthly_peaks[month] = max(monthly_peaks.get(month, realized), equity)
            monthly_dd[month] = max(monthly_dd[month], monthly_peaks[month] - equity)
        realized += trade["net"]
    month_values = {m: round(monthly[m], 6) for m in months}
    if not math.isclose(sum(monthly.values()), realized, abs_tol=1e-7):
        raise ValueError("monthly exit ledger fails annual net reconciliation")
    return {"trades": len(trades), "net": round(realized, 6),
            "positive_months": sum(v > 0 for v in month_values.values()),
            "worst_month": min(month_values.values()),
            "annual_observed_m1_drawdown": round(annual_dd, 6),
            "monthly": month_values,
            "monthly_observed_m1_drawdown": {m: round(monthly_dd[m], 6) for m in months},
            "source_valid_days": len(days),
            "source_bid_reference_not_broker_execution": True}


def run(source):
    with open(source, "rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    if sha != SOURCE_SHA:
        raise ValueError("source SHA mismatch")
    results = {"source_sha256": sha, "family": "NRF-FAC-027",
               "frozen_grid": 16, "independent_hypotheses": 1,
               "years": [2012, 2013], "annual_backtests": 32,
               "monthly_points": 384, "all_in_roundtrip_fee_usd_oz": FEE,
               "results": []}
    with zipfile.ZipFile(source) as archive:
        frames = {y: read_year(archive, y) for y in (2012, 2013)}
    day_sets = {y: signal_days(frames[y]) for y in (2012, 2013)}
    for config in GRID:
        yearly = {str(y): simulate(frames[y], config, days=day_sets[y]) for y in (2012, 2013)}
        results["results"].append({"config": config, "yearly": yearly,
            "positive_months_24": sum(x["positive_months"] for x in yearly.values()),
            "net_two_years": round(sum(x["net"] for x in yearly.values()), 6)})
    # Deterministic priority arbitration across all correlated settings.
    # Exploratory shared-capacity diagnostic, NOT independent OOS evidence.
    results["shared_priority_portfolio"] = {
        str(y): simulate(frames[y], GRID, days=day_sets[y]) for y in (2012, 2013)
    }
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"configs": len(result["results"]), "annual": 32,
                      "best_months": max(r["positive_months_24"] for r in result["results"])}, indent=2))
