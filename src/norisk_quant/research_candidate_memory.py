"""Bounded, explainable TRAINING-ONLY evolutionary memory.

All candidate-year records are independently reconciled before selection.
Only 128 active parents are retained; every explored identity stays in a
separate immutable history. Ranking never touches holdout/forward results.
"""
from __future__ import annotations

from norisk_quant.research_evolution import _formula
from norisk_quant.research_training_integrity import training_summary

MAX_ACTIVE = 128
MAX_UNIVERSE = 256
RECORD_METRICS = frozenset({
    "months", "net_usd_per_oz", "trades", "fees_usd", "positive_months",
    "uncertain_gap_trades", "synthetic_forced_closures", "accounting",
})


def _failure_reasons(summary: dict, records: list[dict]) -> list[str]:
    """Descriptive training diagnostics, not claims about future causation."""
    reasons = []
    if summary["trades"] < 30:
        reasons.append("INSUFFICIENT_TRADES")
    if summary["net_usd_per_oz"] <= 0:
        reasons.append("NONPOSITIVE_TRAINING_NET")
    if summary["positive_months"] * 5 < summary["total_months"] * 3:
        reasons.append("LESS_THAN_60_PERCENT_POSITIVE_MONTHS")
    if any(row["metrics"]["net_usd_per_oz"] <= 0 for row in records):
        reasons.append("NONPOSITIVE_TRAINING_YEAR")
    if summary["gap_exposed_trades"] > 0:
        reasons.append("UNCERTAIN_GAP_EXPOSURE")
    if summary["forced_closures"] > 0:
        reasons.append("FORCED_END_OF_DATA")
    return reasons or ["TRAINING_HEURISTIC_ONLY_NOT_OOS"]


def select_training_memory(candidates: list[dict], years: tuple[int, ...],
                           *, limit: int = MAX_ACTIVE) -> dict:
    """Rank a fully reconciled history and bound the next *active* parent pool.

    Every candidate must have exactly the frozen year universe and complete
    monthly, fee and accounting checks. The returned "all_identities" is
    never truncated: exploration history must prevent rediscovery of evicted
    candidates in later generations.
    """
    if (type(candidates) is not list or not 1 <= len(candidates) <= MAX_UNIVERSE
            or type(limit) is not int or not 1 <= limit <= MAX_ACTIVE
            or type(years) is not tuple):
        raise ValueError("Invalid bounded training candidate universe")
    ranked, seen = [], set()
    for candidate in candidates:
        if (type(candidate) is not dict
                or set(candidate) != {"formula", "records"}
                or type(candidate["records"]) is not list):
            raise ValueError("Unexpected training candidate envelope")
        if any(type(record) is not dict or set(record) != {"year", "metrics"}
               or type(record["metrics"]) is not dict
               or set(record["metrics"]) != RECORD_METRICS
               for record in candidate["records"]):
            raise ValueError("Candidate evidence must contain only frozen training metrics")
        identity = _formula(candidate["formula"]).identity()
        if identity in seen:
            raise ValueError("Duplicate training candidate identity")
        seen.add(identity)
        summary = training_summary(candidate["records"], years)
        ranked.append((identity, candidate, summary,
                       _failure_reasons(summary, candidate["records"])))
    ranked.sort(key=lambda x: (-x[2]["training_score"],
                               -x[2]["net_usd_per_oz"], x[0]))
    kept = ranked[:limit]
    dropped = ranked[limit:]
    def describe(x):
        identity, _, summary, reasons = x
        return {"identity": identity,
                "training_score": summary["training_score"],
                "net_usd_per_oz": summary["net_usd_per_oz"],
                "positive_months": summary["positive_months"],
                "total_months": summary["total_months"],
                "max_month_end_drawdown_usd_per_oz":
                    summary["max_month_end_drawdown_usd_per_oz"],
                "screen": summary["screen"],
                "failure_reasons": reasons,
                "independent_oos_proven": False}
    return {
        "active_candidates": [x[1] for x in kept],
        "all_identities": sorted(seen),
        "selected": [describe(x) for x in kept],
        "evicted": [describe(x) for x in dropped],
        "universe_size": len(ranked),
        "active_size": len(kept),
        "evicted_count": len(dropped),
        "selection_method": "RECONCILED_TRAINING_SCORE_ONLY_NOT_OOS",
        "independent_oos_proven": False,
        "live_trading_authorized": False,
    }
