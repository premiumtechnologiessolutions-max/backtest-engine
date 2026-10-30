"""FAC026 frozen source structural feasibility scan (NO fills, P/L or daily halt).

Original private ZIP is read locally after exact SHA256 verification. Only
aggregated counts are emitted; no raw M1 BID/ASK data is written to GitHub.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"


def candles(df, rule, expected):
    """Only fully observed, contiguous UTC minutes can form an M15/H1 candle."""
    x = df.resample(rule, closed="left", label="right").agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"),
        n=("o", "count"), first=("ts", "min"), last=("ts", "max"))
    x["full"] = ((x.n == expected) &
                 ((x["last"] - x["first"]) == (expected - 1) * 60))
    return x


def load_year(archive, year):
    df = pd.DataFrame(json.loads(archive.read(f"{year}.json")))
    if (not df.ts.is_monotonic_increasing or df.ts.duplicated().any()
            or not np.all(np.diff(df.ts.to_numpy()) >= 60)
            or not (df.ts % 60 == 0).all()):
        raise ValueError("Unordered, duplicate or unaligned original M1 timestamps")
    for column in ("o", "h", "l", "c", "ao", "ah", "al", "ac"):
        if not np.isfinite(df[column]).all() or not (df[column] > 0).all():
            raise ValueError("Nonfinite/nonpositive original quote")
    if not ((df.ao >= df.o).all() and (df.al >= df.l).all()
            and (df.ah >= df.h).all() and (df.ac >= df.c).all()):
        raise ValueError("Invalid paired BID/ASK ordering")
    if not ((df.l <= df[["o", "c"]].min(axis=1)).all()
            and (df[["o", "c"]].max(axis=1) <= df.h).all()
            and (df.al <= df[["ao", "ac"]].min(axis=1)).all()
            and (df[["ao", "ac"]].max(axis=1) <= df.ah).all()):
        raise ValueError("Invalid original quote OHLC")
    df.index = pd.to_datetime(df.ts, unit="s", utc=True)
    return df


def signals(df, n, compression, efficiency, session):
    """Vectorized pre-halt structural upper bound, not executable signals."""
    m = candles(df, "15min", 15)
    h = candles(df, "1h", 60)
    full = m.full.to_numpy()
    groups = (~full).cumsum()
    run = pd.Series(np.where(full, 1, 0), index=m.index).groupby(groups).cumsum().to_numpy()
    complete_context = run >= 2 * n + 1
    ranges = m.h - m.l
    compressed = ranges.shift(1).rolling(n, min_periods=n).mean()
    baseline = ranges.shift(n + 1).rolling(n, min_periods=n).mean()
    highest = m.h.shift(1).rolling(n, min_periods=n).max()
    lowest = m.l.shift(1).rolling(n, min_periods=n).min()
    side = np.where(m.c > highest, 1, np.where(m.c < lowest, -1, 0))
    normalized_risk = np.maximum(ranges, m.c * 0.0004) / m.c
    h["contiguous"] = (h.full & h.full.shift(1, fill_value=False)
                       & h.full.shift(2, fill_value=False))
    h["move"] = h.c - h.o.shift(2)
    h["ranges"] = (h.h - h.l).rolling(3, min_periods=3).sum()
    h["efficiency"] = np.where(h.ranges > 0, h.move.abs() / h.ranges, 0)
    known_h1 = h[["contiguous", "move", "efficiency"]].reindex(
        m.index, method="ffill")
    decision = m.index + pd.Timedelta(minutes=1)
    ny_hour = decision.tz_convert("America/New_York").hour
    mask = (complete_context & (compressed <= compression * baseline).to_numpy()
            & (side != 0) & (normalized_risk <= 0.002).to_numpy()
            & (ny_hour >= session[0]) & (ny_hour < session[1])
            & known_h1.contiguous.eq(True).to_numpy()
            & (side * known_h1.move.to_numpy() > 0)
            & (known_h1.efficiency.to_numpy() >= efficiency))
    observed_triggers = m.index[mask]
    # Decision is at trigger end +1 minute; first strictly later open is +2.
    # This is only an observed-open availability check, never a fill.
    eligible_next_open = observed_triggers + pd.Timedelta(minutes=2)
    return observed_triggers, observed_triggers[eligible_next_open.isin(df.index)]




def parity_for_variant(df, n, compression, efficiency, session, *, raw=None,
                       negative_per_month=8):
    """Independently compare ALL vectorized positives and sampled negatives.

    Only frozen pre-halt structural intents are checked. This is not a trade,
    next-open fill, complete negative scan, or a portfolio backtest.
    No quote values or individual timestamps are returned.
    """
    from scripts.research_fac026_compression_breakout import evaluate, frozen_specs

    if type(negative_per_month) is not int or not 1 <= negative_per_month <= 64:
        raise ValueError("Invalid deterministic parity sample budget")
    key = (n, compression, efficiency, tuple(session))
    candidates = [s for s in frozen_specs()
                  if (s["params"]["window"], s["params"]["compression"],
                      s["params"]["h1_efficiency"],
                      tuple(s["params"]["session"])) == key
                  and s["params"]["daily_loss_halt"] == 2.0]
    if len(candidates) != 1:
        raise ValueError("Not a frozen FAC026 structural variant")
    spec = candidates[0]
    if raw is None:
        raw, _ = signals(df, n, compression, efficiency, session)
    positives = set(raw)
    m = candles(df, "15min", 15)
    h = candles(df, "1h", 60)

    def context(end):
        mb = m.loc[:end].tail(2 * n + 1)
        hb = h.loc[:end].tail(3)
        if len(mb) != 2 * n + 1 or len(hb) != 3:
            return None
        if not mb.full.all() or not hb.full.all():
            return None
        if not (mb.index.to_series().diff().iloc[1:] ==
                pd.Timedelta(minutes=15)).all():
            return None
        if not (hb.index.to_series().diff().iloc[1:] ==
                pd.Timedelta(hours=1)).all():
            return None
        def records(frame):
            return [{"end_at": end_at.to_pydatetime(),
                     "open": float(row.o), "high": float(row.h),
                     "low": float(row.l), "close": float(row.c),
                     "observed_m1_count": int(row.n)}
                    for end_at, row in frame.iterrows()]
        return records(mb), records(hb)

    negatives = set()
    for year, month in sorted({(t.year, t.month) for t in m.index}):
        choices = [end for end in m.index
                   if end.year == year and end.month == month
                   and end not in positives
                   and session[0] <= (end + pd.Timedelta(minutes=1))
                   .tz_convert("America/New_York").hour < session[1]
                   and context(end) is not None]
        stride = max(1, len(choices) // negative_per_month)
        negatives.update(choices[::stride][:negative_per_month])
    positive_checks = negative_checks = 0
    for end in sorted(positives | negatives):
        bars = context(end)
        if bars is None:
            if end in positives:
                raise ValueError("FAC026 scanner positive lacks causal context")
            continue
        result = evaluate((end + pd.Timedelta(minutes=1)).to_pydatetime(),
                          bars[0], bars[1], [], spec=spec)
        actual = result["status"] == "ELIGIBLE_RESEARCH_INTENT_ONLY"
        expected = end in positives
        if actual != expected:
            raise ValueError("FAC026 vectorized/frozen evaluator signal mismatch")
        if expected:
            positive_checks += 1
        else:
            negative_checks += 1
    return {"positive_checks": positive_checks,
            "sampled_negative_checks": negative_checks,
            "negative_sampling": "deterministic_month_stratified_not_exhaustive",
            "daily_halt_evaluated": False, "executed_trades": 0}

def run(path, years=(2012, 2013), *, parity=False):
    if (not years or len(set(years)) != len(years)
            or any(type(year) is not int or year not in (2012, 2013)
                   for year in years)):
        raise ValueError("Only unique preregistered exposed design years 2012/2013 allowed")
    with open(path, "rb") as source:
        sha = hashlib.file_digest(source, "sha256").hexdigest()
    if sha != SOURCE_SHA:
        raise ValueError("Gold ZIP SHA mismatch")
    # 16 structural variants; each is duplicated by two untested daily halts.
    variants = [(n, c, e, s) for n in (8, 12)
                for c in (0.65, 0.80) for e in (0.35, 0.55)
                for s in ((8, 12), (9, 13))]
    result = {
        "source_sha256": sha, "years": list(years), "hypothesis": "NRF-FAC-026",
        "frozen_correlated_settings": 32, "structural_base_variants": 16,
        "daily_halt_applied": False, "executed_trades": 0,
        "monthly_net_usd_per_oz": "N/A", "monthly_floating_drawdown": "N/A",
        "years_detail": {},
    }
    with zipfile.ZipFile(path) as archive:
        for year in years:
            df = load_year(archive, year)
            detail = {"observed_m1": len(df), "settings": []}
            unique_triggers, unique_next_opens = set(), set()
            for n, c, e, session in variants:
                triggers, available = signals(df, n, c, e, session)
                unique_triggers.update(triggers)
                unique_next_opens.update(available)
                monthly = pd.Series(1, index=available).groupby(
                    available.tz_localize(None).to_period("M")).sum()
                if parity:
                    detail.setdefault("causal_evaluator_parity", []).append({
                        "window": n, "compression": c, "h1_efficiency": e,
                        "session": list(session),
                        **parity_for_variant(df, n, c, e, session, raw=triggers),
                    })
                detail["settings"].append({
                    "window": n, "compression": c, "h1_efficiency": e,
                    "session": list(session),
                    "structural_signals": len(triggers),
                    "observed_entry_next_open": len(available),
                    "monthly_counts": {str(period): int(count)
                                       for period, count in monthly.items()},
                })
            detail["unique_structural_signal_times_across_16_variants"] = len(unique_triggers)
            detail["unique_observed_next_open_times_across_16_variants"] = len(unique_next_opens)
            detail["months_with_any_structural_signal"] = len(
                {str(timestamp.to_period("M")) for timestamp in unique_triggers})
            result["years_detail"][str(year)] = detail
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path, help="Local original Gold data.zip; NEVER upload")
    parser.add_argument("--out", type=Path, default=Path("fac026_structural.json"))
    parser.add_argument("--parity", action="store_true",
                        help="Independently audit frozen evaluator vs vectorized signals")
    args = parser.parse_args(argv)
    result = run(args.zip, parity=args.parity)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    for year, detail in result["years_detail"].items():
        print(year, "M1", detail["observed_m1"],
              "unique structural signals", detail["unique_structural_signal_times_across_16_variants"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
