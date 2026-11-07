"""Original-source FAC025 entry-open spread stress: diagnostics, NOT backtests.

Reconstruct the unchanged FAC025-ENTRY-A structural candidate set from observed
UTC M1 bars. Report only aggregate entry-open BID/ASK spread distributions.
No fills, simulated P/L, receipt authentication, or independent OOS claims.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo
import zipfile

SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
MINUTE, QUARTER, HOUR = 60, 900, 3600
NY = ZoneInfo("America/New_York")
BUCKETS = ("ALL", "NY_08_12", "NY_09_13")


def _percentile_nearest_rank(values: list[float], numerator: int) -> float:
    """Deterministic nearest-rank percentile, not a smoothed price estimate."""
    if not values or not 0 < numerator <= 100:
        raise ValueError("Nonempty sample and percentile 1..100 required")
    ordered = sorted(values)
    return ordered[(numerator * len(ordered) + 99) // 100 - 1]


def candidate_entry_open_spreads(rows: list[dict]) -> dict:
    """Count pre-entry structural signals; observe *only* next M1 open spread.

    Signal decision is at completed candidate M15 end + 60s. The next
    eligible observed open is end + 120s. Do not interpolate absent minutes.
    For each candidate we use only the prior four complete M15 and two
    completed H1 bars ending before the candidate M15 begins.
    """
    if type(rows) is not list:
        raise ValueError("Source year must be a list")
    bars: dict[int, tuple[float, float, float]] = {}
    entry_open: dict[int, tuple[float, float]] = {}
    group: list[dict] = []
    group_start = None
    previous = None
    counts = defaultdict(int)

    def flush() -> None:
        if (len(group) == 15 and group[0]["ts"] == group_start
                and group[-1]["ts"] == group_start + 14 * MINUTE):
            bars[group_start + QUARTER] = (
                max(x["h"] for x in group), min(x["l"] for x in group), group[-1]["c"])

    for row in rows:
        if type(row) is not dict or not all(k in row for k in
                ("ts", "o", "h", "l", "c", "ao", "ah", "al", "ac")):
            raise ValueError("Malformed original M1 row")
        stamp = row["ts"]
        if type(stamp) is not int or stamp % MINUTE or (previous is not None and stamp <= previous):
            raise ValueError("Unsorted, duplicate or nonminute timestamp")
        for prefix in ("", "a"):
            o, h, l, c = (row[prefix + k] for k in ("o", "h", "l", "c"))
            if (any(type(v) not in (float, int) or not math.isfinite(v) or v <= 0
                    for v in (o, h, l, c)) or not l <= min(o, c) <= max(o, c) <= h):
                raise ValueError("Invalid original BID/ASK OHLC")
        if any(row["a" + k] < row[k] for k in ("o", "h", "l", "c")):
            raise ValueError("Crossed original BID/ASK OHLC")
        entry_open[stamp] = (row["o"], row["ao"])
        start = stamp // QUARTER * QUARTER
        if start != group_start:
            flush()
            group_start, group = start, []
        group.append(row)
        previous = stamp
    flush()

    monthly: dict[str, dict[str, dict[str, object]]] = {}
    for end in sorted(bars):
        prev = [bars.get(end - k * QUARTER) for k in (4, 3, 2, 1)]
        if any(x is None for x in prev):
            continue
        cutoff = ((end - QUARTER) // HOUR) * HOUR

        def h1_close(at: int) -> float | None:
            four = [bars.get(at - k * QUARTER) for k in (3, 2, 1, 0)]
            return four[-1][2] if all(x is not None for x in four) else None

        older, newer = h1_close(cutoff - HOUR), h1_close(cutoff)
        if older is None or newer is None:
            continue
        high, low, close = bars[end]
        bull = low < min(x[1] for x in prev) < close and newer > older
        bear = high > max(x[0] for x in prev) > close and newer < older
        if bull == bear:
            continue
        counts["structural_candidates"] += 1
        risk = max((close - low) if bull else (high - close), close * 0.0004)
        if risk > close * 0.0015:
            continue
        counts["normalized_risk_candidates"] += 1
        entry = entry_open.get(end + 2 * MINUTE)
        if entry is None:
            continue
        counts["observed_next_open_candidates"] += 1
        spread = entry[1] - entry[0]
        month = datetime.fromtimestamp(end, timezone.utc).strftime("%Y-%m")
        ny_hour = datetime.fromtimestamp(end + MINUTE, timezone.utc).astimezone(NY).hour
        labels = ["ALL"]
        if 8 <= ny_hour < 12:
            labels.append("NY_08_12")
        if 9 <= ny_hour < 13:
            labels.append("NY_09_13")
        for label in labels:
            bucket = monthly.setdefault(month, {}).setdefault(label, {"spreads": [], "buy": 0, "sell": 0})
            bucket["spreads"].append(spread)
            bucket["buy" if bull else "sell"] += 1
            counts[label] += 1

    summarized = {}
    for month, groups in sorted(monthly.items()):
        summarized[month] = {}
        for label, item in sorted(groups.items()):
            values = item["spreads"]
            summarized[month][label] = {
                "observed_candidate_opens": len(values),
                "buy": item["buy"], "sell": item["sell"],
                "spread_gt_fixed_fee_count": sum(x > 0.40 + 1e-9 for x in values),
                "spread_median_usd_per_oz": round(median(values), 6),
                "spread_p95_usd_per_oz": round(_percentile_nearest_rank(values, 95), 6),
                "spread_max_usd_per_oz": round(max(values), 6),
            }
    return {"counts": dict(counts), "months": summarized}


def analyze_source(private_zip: str | Path, years=(2012, 2013, 2014, 2015, 2016)) -> dict:
    path = Path(private_zip)
    digest = sha256(path.read_bytes()).hexdigest()
    if digest != SOURCE_SHA:
        raise ValueError("Private source SHA256 mismatch")
    results = {}
    # Independent original structural audit provides a fail-closed count parity
    # gate. This does not authenticate quote receipt time or executable fills.
    try:
        from scripts.research_fac025_source_feasibility import inspect_year
    except ModuleNotFoundError as exc:
        if exc.name != "scripts":
            raise
        from research_fac025_source_feasibility import inspect_year
    with zipfile.ZipFile(path) as archive:
        for year in years:
            rows = json.loads(archive.read(f"{year}.json"))
            result = candidate_entry_open_spreads(rows)
            ref = inspect_year(rows)
            comparisons = {
                "structural_candidates": "sweep_h1_directional_candidates",
                "normalized_risk_candidates": "normalized_risk_passed_intents",
                "observed_next_open_candidates": "next_minute_open_observed_not_fill",
                "NY_08_12": "ny_08_12_observed_open_candidates",
                "NY_09_13": "ny_09_13_observed_open_candidates",
            }
            for ours, theirs in comparisons.items():
                if result["counts"].get(ours, 0) != ref["counts"].get(theirs, 0):
                    raise ValueError(f"Independent FAC025 candidate count parity failed: {year} {ours}")
            results[str(year)] = result
    return {
        "status": "ORIGINAL_SOURCE_STRUCTURAL_ENTRY_SPREAD_DIAGNOSTIC_ONLY",
        "source_sha256": digest, "frozen_policy": "FAC025-ENTRY-A",
        "source_receipt_authenticated": False, "actual_trades": 0,
        "portfolio_backtest_verified": False, "monthly_net_pnl": "N/A",
        "observed_m1_floating_drawdown": "N/A", "approved_strategies": 0,
        "fee_usd_per_oz_all_in_roundtrip_unchanged": 0.40,
        "spread_is_diagnostic_not_additional_fee": True,
        "years": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_zip", type=Path)
    parser.add_argument("--years", type=int, nargs="+", default=[2012, 2013, 2014, 2015, 2016])
    args = parser.parse_args()
    print(json.dumps(analyze_source(args.private_zip, args.years), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
