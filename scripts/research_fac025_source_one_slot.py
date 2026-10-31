"""Frozen FAC025 original-source BID-reference one-slot research replay.

No live orders, no authenticated broker fills, no canonical-engine parity claim.
Raw Gold M1 must stay local. Results are historical-exposed only.
"""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import json
import math
import zipfile
import numpy as np

SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
FEE = 0.40
NY = ZoneInfo("America/New_York")
MINUTE, QUARTER, HOUR = 60, 900, 3600


def frozen_specs():
    fields = ("lookback", "min_range_ratio", "max_range_ratio", "daily_loss_halt", "session_start_hour", "session_end_hour")
    specs = []
    for n, lo, hi, halt, session in product((4, 8, 12), ("0.0004", "0.0008"), ("0.003", "0.006"), ("2", "4", "6"), ((8, 12), (9, 13))):
        params = dict(zip(fields, (n, lo, hi, halt, *session)))
        payload = {"hypothesis": "NRF-FAC-025", "spec_version": 1, "parameters": params}
        fingerprint = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
        specs.append({"id": f"FAC025-{len(specs)+1:03d}", "parameters": params, "fingerprint": fingerprint})
    assert len(specs) == len({s["fingerprint"] for s in specs}) == 72
    return specs


def validate_source(rows):
    if not rows:
        raise ValueError("Missing original M1 observations")
    last = None
    for r in rows:
        if type(r) is not dict or any(k not in r for k in ("ts", "o", "h", "l", "c", "ao", "ah", "al", "ac")):
            raise ValueError("Invalid original source row")
        t = r["ts"]
        if type(t) is not int or t % 60 or (last is not None and t <= last):
            raise ValueError("Duplicate, unsorted or non-minute UTC timestamp")
        last = t
        for prefix in ("", "a"):
            o, h, l, c = (r[prefix + k] for k in ("o", "h", "l", "c"))
            if any(type(x) not in (float, int) or not math.isfinite(x) or x <= 0 for x in (o, h, l, c)) or not l <= min(o, c) <= max(o, c) <= h:
                raise ValueError("Invalid source quote OHLC")
        if any(r["a" + k] < r[k] for k in ("o", "h", "l", "c")):
            raise ValueError("Crossed paired BID/ASK quote")


def generate_candidates(rows):
    """Use completed contiguous M15/H1 only; no future values in signal."""
    opens = {r["ts"]: i for i, r in enumerate(rows)}
    m15, groups = {}, []
    start = None
    def flush():
        if len(groups) == 15 and all(r["ts"] == start + 60 * i for i, r in enumerate(groups)):
            m15[start + QUARTER] = (max(r["h"] for r in groups), min(r["l"] for r in groups), groups[-1]["c"])
    for r in rows:
        bucket = r["ts"] // QUARTER * QUARTER
        if bucket != start:
            if groups:
                flush()
            start, groups = bucket, []
        groups.append(r)
    flush()
    candidates = []
    counts = Counter()
    for end in sorted(m15):
        previous = [m15.get(end - QUARTER * k) for k in (4, 3, 2, 1)]
        if any(x is None for x in previous):
            continue
        cutoff = (end - QUARTER) // HOUR * HOUR
        def h1_close(h1_end):
            group = [m15.get(h1_end - QUARTER * k) for k in (3, 2, 1, 0)]
            return group[-1][2] if all(x is not None for x in group) else None
        older, newer = h1_close(cutoff - HOUR), h1_close(cutoff)
        if older is None or newer is None:
            continue
        high, low, close = m15[end]
        support = min(x[1] for x in previous)
        resistance = max(x[0] for x in previous)
        buy = low < support < close and newer > older
        sell = high > resistance > close and newer < older
        if buy == sell:
            continue
        counts["directional_sweep"] += 1
        risk = max(close - low if buy else high - close, close * 0.0004)
        if risk > close * 0.0015:
            counts["risk_rejected"] += 1
            continue
        counts["risk_passed"] += 1
        decision, entry_at = end + MINUTE, end + 2 * MINUTE
        if entry_at not in opens:
            counts["no_exact_next_open"] += 1
            continue
        ratios = {}
        for n in (4, 8, 12):
            window = [m15.get(end - QUARTER * k) for k in range(n)]
            if all(x is not None for x in window):
                ratios[n] = sum(x[0] - x[1] for x in window) / (n * close)
        candidates.append({"decision": decision, "entry_at": entry_at,
                           "entry_idx": opens[entry_at], "side": 1 if buy else -1,
                           "risk": risk, "ratios": ratios,
                           "ny_hour": datetime.fromtimestamp(decision, timezone.utc).astimezone(NY).hour,
                           "ny_day": datetime.fromtimestamp(decision, timezone.utc).astimezone(NY).date().isoformat()})
    counts["observed_entry_candidates"] = len(candidates)
    return candidates, dict(counts)


def settle_trade(rows, candidate):
    """BID-only canonical proxy, one fixed $0.40 all-in fee; stop-first."""
    idx, side, risk = candidate["entry_idx"], candidate["side"], candidate["risk"]
    entry = rows[idx]["o"]
    stop = entry - side * risk
    target = entry + side * risk * 1.5
    for j in range(idx, len(rows)):
        bar = rows[j]
        o, h, l = bar["o"], bar["h"], bar["l"]
        if (side == 1 and o <= stop) or (side == -1 and o >= stop):
            price, reason = o, "adverse_open_stop"
        elif (side == 1 and o >= target) or (side == -1 and o <= target):
            price, reason = target, "favorable_open_target_capped"
        elif (side == 1 and l <= stop) or (side == -1 and h >= stop):
            price, reason = stop, "stop_first"
        elif (side == 1 and h >= target) or (side == -1 and l <= target):
            price, reason = target, "target"
        elif j == len(rows) - 1:
            price, reason = bar["c"], "end_of_year_forced"
        else:
            continue
        return {**candidate, "entry_price": entry, "exit_idx": j,
                "exit_at": rows[j]["ts"], "exit_price": price,
                "exit_reason": reason, "exit_ny_day": datetime.fromtimestamp(rows[j]["ts"], timezone.utc).astimezone(NY).date().isoformat(), "gross": side * (price - entry),
                "fee": FEE, "net": side * (price - entry) - FEE}
    raise AssertionError("Unreachable empty exit path")


def eligible(candidate, spec, closed_by_day):
    p = spec["parameters"]
    if not p["session_start_hour"] <= candidate["ny_hour"] < p["session_end_hour"]:
        return False
    ratio = candidate["ratios"].get(p["lookback"])
    if ratio is None or not float(p["min_range_ratio"]) <= ratio <= float(p["max_range_ratio"]):
        return False
    realized = closed_by_day.get(candidate["ny_day"], 0.0)
    return realized > -float(p["daily_loss_halt"])


def replay(candidates, rows, specs):
    """One slot and one realized ledger; choose lowest eligible frozen ID."""
    selected, skipped_capacity, skipped_gate = [], 0, 0
    previous_exit = -1
    realized_by_day = {}
    unsettled_last = None
    for candidate in candidates:
        if candidate["decision"] <= previous_exit:
            skipped_capacity += 1
            continue
        if unsettled_last is not None:
            day = unsettled_last["exit_ny_day"]
            realized_by_day[day] = realized_by_day.get(day, 0.0) + unsettled_last["net"]
            unsettled_last = None
        spec = next((s for s in specs if eligible(candidate, s, realized_by_day)), None)
        if spec is None:
            skipped_gate += 1
            continue
        trade = {**candidate["settled"], "spec_id": spec["id"]} if "settled" in candidate else settle_trade(rows, candidate)
        unsettled_last = trade
        selected.append(trade)
        previous_exit = trade["exit_at"]
    return selected, {"skipped_capacity": skipped_capacity, "skipped_gate": skipped_gate}


def source_context(rows):
    close = np.fromiter((r["c"] for r in rows), dtype=np.float64, count=len(rows))
    counts = Counter(datetime.fromtimestamp(r["ts"], timezone.utc).strftime("%Y-%m") for r in rows)
    return close, dict(counts)


def score(rows, trades, *, context=None):
    """Exit-booked monthly net and actually observed M1 close-equity marks."""
    if context is None:
        context = source_context(rows)
    close, counts = context
    marks = np.empty(len(rows), dtype=np.float64)
    monthly = {m: {"net_usd_per_oz": 0.0, "trades": 0, "fees_usd_per_oz": 0.0,
                   "observed_m1": n, "month_local_observed_m1_close_dd_usd_per_oz": 0.0}
               for m, n in counts.items()}
    realized, cursor = 0.0, 0
    for trade in trades:
        a, b = trade["entry_idx"], trade["exit_idx"]
        if a < cursor or b < a:
            raise ValueError("Overlapping or invalid one-slot ledger")
        marks[cursor:a] = realized
        if b > a:
            marks[a:b] = realized + trade["side"] * (close[a:b] - trade["entry_price"]) - FEE
        realized += trade["net"]
        cursor = b
        m = datetime.fromtimestamp(trade["exit_at"], timezone.utc).strftime("%Y-%m")
        monthly[m]["net_usd_per_oz"] += trade["net"]
        monthly[m]["fees_usd_per_oz"] += FEE
        monthly[m]["trades"] += 1
    marks[cursor:] = realized
    peak = np.maximum.accumulate(np.r_[0.0, marks])
    global_dd = float(np.max(peak - np.r_[0.0, marks]))
    last_month_mark = 0.0
    offset = 0
    for m, stats in monthly.items():
        n = stats["observed_m1"]
        block = np.r_[last_month_mark, marks[offset:offset + n]]
        stats["month_local_observed_m1_close_dd_usd_per_oz"] = float(np.max(np.maximum.accumulate(block) - block))
        last_month_mark = float(marks[offset + n - 1])
        offset += n
        stats["net_usd_per_oz"] = round(stats["net_usd_per_oz"], 8)
        stats["fees_usd_per_oz"] = round(stats["fees_usd_per_oz"], 8)
        stats["month_local_observed_m1_close_dd_usd_per_oz"] = round(stats["month_local_observed_m1_close_dd_usd_per_oz"], 8)
    net = sum(t["net"] for t in trades)
    if not math.isclose(net, sum(x["net_usd_per_oz"] for x in monthly.values()), abs_tol=1e-6):
        raise AssertionError("Monthly booked P/L mismatch")
    if not math.isclose(FEE * len(trades), sum(x["fees_usd_per_oz"] for x in monthly.values()), abs_tol=1e-6):
        raise AssertionError("Roundtrip fees mismatch")
    return {"trades": len(trades), "net_usd_per_oz": round(net, 8),
            "fees_usd_per_oz": round(FEE * len(trades), 8),
            "positive_months": sum(x["net_usd_per_oz"] > 0 for x in monthly.values()),
            "months_observed": len(monthly),
            "worst_month_utc": min(monthly, key=lambda m: monthly[m]["net_usd_per_oz"]),
            "max_observed_m1_global_close_dd_usd_per_oz": round(global_dd, 8),
            "max_observed_m1_month_local_close_dd_usd_per_oz": max(x["month_local_observed_m1_close_dd_usd_per_oz"] for x in monthly.values()),
            "forced_closes": sum(t["exit_reason"] == "end_of_year_forced" for t in trades),
            "monthly": monthly}


def run_source(zip_path, years=(2012, 2013)):
    path = Path(zip_path)
    if sha256(path.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError("Private original ZIP SHA mismatch")
    specs = frozen_specs()
    results = {}
    with zipfile.ZipFile(path) as archive:
        for year in years:
            rows = json.loads(archive.read(f"{year}.json"))
            validate_source(rows)
            candidates, counts = generate_candidates(rows)
            context = source_context(rows)
            for candidate in candidates:
                candidate["settled"] = settle_trade(rows, candidate)
            portfolios = {}
            for spec in specs:
                trades, skipped = replay(candidates, rows, [spec])
                portfolios[spec["id"]] = {**score(rows, trades, context=context), **skipped}
            trades, skipped = replay(candidates, rows, specs)
            unified = {**score(rows, trades, context=context), **skipped}
            results[str(year)] = {"observed_m1": len(rows), "candidate_counts": counts,
                                  "shared_priority_one_slot": unified,
                                  "standalone_specs": portfolios}
    return {"status": "ORIGINAL_SOURCE_BID_PROXY_INDEPENDENT_REPLAY_CANONICAL_PARITY_PENDING_HISTORICAL_EXPOSED",
            "source_sha256": SOURCE_SHA, "fee_usd_per_oz_all_in": FEE,
            "independent_hypotheses": 1, "correlated_specs": len(specs),
            "shared_capacity_positions": 1, "source_authenticated": False,
            "canonical_parity_verified": False, "clean_oos": False,
            "approved_strategies": 0, "years": results}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("private_zip", type=Path)
    p.add_argument("--years", nargs="+", type=int, default=[2012, 2013])
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    report = run_source(args.private_zip, args.years)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps({"status": report["status"], "years": {k: {"shared": v["shared_priority_one_slot"], "candidate_counts": v["candidate_counts"]} for k,v in report["years"].items()}}, default=str)[:1500])

if __name__ == "__main__":
    main()
