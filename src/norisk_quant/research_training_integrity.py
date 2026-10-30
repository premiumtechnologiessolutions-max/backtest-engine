"""Frozen, training-only arithmetic-candidate evidence reconciliation.

This is a deterministic ranking-preflight, NOT a strategy optimizer, a
significance test, independent OOS, or permission to trade. Historical years
examined by prior research are considered exposed. Every evidence input must
pass the full-year calendar, fee and summary arithmetic checks BEFORE it can
influence an adaptive research controller's selection.

No market data, mutable files, network calls or arbitrary Python evaluation.
"""
from __future__ import annotations

import math


def _finite(value: object, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be finite numeric (not bool/string)")
    return float(value)


def training_summary(records: list[dict], years: tuple[int, ...], *,
                     fee_per_trade: float = 0.40) -> dict:
    """Reconcile all frozen training years and return an exploratory screen.

    records: [{'year': YYYY, 'metrics': {'months': {'YYYY-MM': net, ...},
              'net_usd_per_oz': net, 'trades': count, 'fees_usd': cost,
              'positive_months': count, 'uncertain_gap_trades': count,
              'synthetic_forced_closures': count, 'accounting': 'PASSED'}}, ...].
    Review years are never accepted. Input record order cannot affect ranking.
    """
    if (type(years) is not tuple or len(years) < 2
            or any(type(y) is not int or not 1900 <= y <= 2100 for y in years)
            or years != tuple(sorted(set(years)))
            or type(records) is not list or len(records) != len(years)):
        raise ValueError("Require >=2 complete, unique chronological training years")
    cost = _finite(fee_per_trade, "fee_per_trade")
    if cost != 0.40:
        raise ValueError("Canonical research cost is exactly $0.40/oz roundtrip")
    by_year = {}
    for record in records:
        if (type(record) is not dict or type(record.get("year")) is not int
                or record["year"] not in years or record["year"] in by_year
                or type(record.get("metrics")) is not dict):
            raise ValueError("Training rows must match the frozen year universe")
        by_year[record["year"]] = record["metrics"]
    if set(by_year) != set(years):
        raise ValueError("Incomplete training universe")
    monthly, total_trades, gap, forced = [], 0, 0, 0
    net, total_fees = 0.0, 0.0
    for year in years:
        record = by_year[year]
        period_map = record.get("months")
        expected = [f"{year}-{month:02d}" for month in range(1, 13)]
        if type(period_map) is not dict or set(period_map) != set(expected):
            raise ValueError("Each year needs precisely its 12 UTC months")
        values = [_finite(period_map[month], month) for month in expected]
        count_fields = ("trades", "positive_months",
                        "uncertain_gap_trades", "synthetic_forced_closures")
        if any(type(record.get(field)) is not int for field in count_fields):
            raise ValueError("Annual counts must be real integers, never boolean")
        trades = record["trades"]
        positive = record["positive_months"]
        gaps = record["uncertain_gap_trades"]
        closes = record["synthetic_forced_closures"]
        if (trades < 0 or not 0 <= gaps <= trades or not 0 <= closes <= trades
                or positive != sum(value > 0 for value in values)
                or record.get("accounting") != "PASSED"):
            raise ValueError("Annual counts or accounting reconciliation invalid")
        actual_net = _finite(record.get("net_usd_per_oz"), "net_usd_per_oz")
        actual_fees = _finite(record.get("fees_usd"), "fees_usd")
        if (not math.isclose(sum(values), actual_net, rel_tol=0, abs_tol=1e-5)
                or not math.isclose(actual_fees, trades * cost,
                                    rel_tol=0, abs_tol=1e-5)):
            raise ValueError("Monthly net or one-charge-per-trade fee mismatch")
        monthly.extend(values)
        total_trades += trades
        net += actual_net
        total_fees += actual_fees
        gap += gaps
        forced += closes
    if not math.isfinite(net) or not math.isfinite(total_fees):
        raise ValueError("Annual totals overflowed across training years")
    net, total_fees = round(net, 8), round(total_fees, 8)
    positive_months = sum(value > 0 for value in monthly)
    high = equity = drawdown = 0.0
    for value in monthly:
        equity += value
        if not math.isfinite(equity):
            raise ValueError("Training equity accumulation overflowed")
        high = max(high, equity)
        drawdown = max(drawdown, high - equity)
        # Individually finite observations can still overflow when subtracting
        # the running equity from an earlier high-water mark. Never allow an
        # infinite drawdown into a ranking or a signed research manifest.
        if not math.isfinite(drawdown):
            raise ValueError("Training month-end drawdown overflowed")
    # Ranking is deliberately a TRAINING heuristic, not a statistical result.
    screened = (total_trades >= 30 and net > 0 and
                positive_months / len(monthly) >= 0.60 and gap == 0
                and forced == 0)
    score = round(100 * positive_months / len(monthly)
                  + min(15, max(-15, net / 100))
                  - min(20, drawdown / 100)
                  - 5 * (gap > 0) - 5 * (forced > 0), 6)
    if total_trades < 30:
        score = -1000.0 - (30 - total_trades)
    return {
        "training_score": score,
        "screen": ("PASSED_TRAIN_HEURISTIC_NOT_OOS" if screened
                   else "REJECTED_TRAIN_HEURISTIC"),
        "positive_months": positive_months,
        "total_months": len(monthly),
        "net_usd_per_oz": net,
        "max_month_end_drawdown_usd_per_oz": round(drawdown, 8),
        "trades": total_trades, "fees_usd": total_fees,
        "gap_exposed_trades": gap, "forced_closures": forced,
        "independent_oos_proven": False, "market_edge_confirmed": False,
    }
