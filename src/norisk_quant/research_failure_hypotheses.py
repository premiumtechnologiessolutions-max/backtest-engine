"""Matched-pair training diagnostics for next-generation arithmetic hypotheses.

Only comparisons where evaluated formulas differ by ONE grammar parameter
are eligible. These are observed retrospective parameter associations, NOT
identification of a causal mechanism or independent forward evidence.
"""
from __future__ import annotations

from dataclasses import asdict
from itertools import combinations

from .research_candidate_memory import (
    MAX_ACTIVE, RECORD_METRICS, _failure_reasons,
)
from .research_evolution import _formula
from .research_training_integrity import training_summary


def analyze_matched_training_pairs(candidates: list[dict],
                                   years: tuple[int, ...], *,
                                   limit: int = 100) -> dict:
    """Independently reconcile 1..128 parents; compare one-field neighbors.

    The "better" direction is chosen *after looking at training scores*
    and is labeled post hoc. No trading recommendation or statistical
    discovery is implied; proposed contrasts require a fresh frozen test.
    """
    if (type(candidates) is not list or not 1 <= len(candidates) <= MAX_ACTIVE
            or type(years) is not tuple
            or type(limit) is not int or not 1 <= limit <= 1000):
        raise ValueError("Invalid bounded matched training evidence")
    evaluated, identities = [], set()
    for candidate in candidates:
        if (type(candidate) is not dict
                or set(candidate) != {"formula", "records"}
                or type(candidate["records"]) is not list
                or any(type(r) is not dict or set(r) != {"year", "metrics"}
                       or type(r["metrics"]) is not dict
                       or set(r["metrics"]) != RECORD_METRICS
                       for r in candidate["records"])):
            raise ValueError("Only canonical frozen training metrics are accepted")
        formula = _formula(candidate["formula"])
        identity = formula.identity()
        if identity in identities:
            raise ValueError("Duplicate evaluated formula")
        identities.add(identity)
        summary = training_summary(candidate["records"], years)
        by_year = {r["year"]: r["metrics"] for r in candidate["records"]}
        months = {f"{y}-{m:02d}": float(by_year[y]["months"][f"{y}-{m:02d}"])
                  for y in years for m in range(1, 13)}
        evaluated.append({
            "identity": identity, "formula": asdict(formula),
            "summary": summary, "months": months, "by_year": by_year,
            "failure_reasons": _failure_reasons(summary, candidate["records"]),
        })
    evaluated.sort(key=lambda x: x["identity"])
    pairs = []
    for first, second in combinations(evaluated, 2):
        different = [key for key in first["formula"]
                     if first["formula"][key] != second["formula"][key]]
        if len(different) != 1:
            continue
        field = different[0]
        # Explicit post-hoc label: the direction is not preregistered.
        winner, loser = sorted(
            (first, second),
            key=lambda c: (-c["summary"]["training_score"],
                           -c["summary"]["net_usd_per_oz"], c["identity"]))
        improved = worsened = unchanged = 0
        by_year_delta = {}
        for y in years:
            deltas = [
                winner["months"][f"{y}-{m:02d}"]
                - loser["months"][f"{y}-{m:02d}"]
                for m in range(1, 13)
            ]
            improved += sum(x > 1e-7 for x in deltas)
            worsened += sum(x < -1e-7 for x in deltas)
            unchanged += sum(abs(x) <= 1e-7 for x in deltas)
            by_year_delta[str(y)] = round(
                winner["by_year"][y]["net_usd_per_oz"]
                - loser["by_year"][y]["net_usd_per_oz"], 8)
        delta = round(
            winner["summary"]["net_usd_per_oz"]
            - loser["summary"]["net_usd_per_oz"], 8)
        both_years = all(x > 0 for x in by_year_delta.values())
        stable = bool(both_years and improved >= worsened
                      and winner["summary"]["trades"] >= 30)
        pairs.append({
            "changed_field": field,
            "from_value": loser["formula"][field],
            "to_value": winner["formula"][field],
            "base_formula_identity": loser["identity"],
            "comparison_formula_identity": winner["identity"],
            "training_net_delta_usd_per_oz": delta,
            "training_score_delta": round(
                winner["summary"]["training_score"]
                - loser["summary"]["training_score"], 6),
            "yearly_net_deltas_usd_per_oz": by_year_delta,
            "months_improved": improved,
            "months_worsened": worsened,
            "months_unchanged": unchanged,
            "total_months": 12 * len(years),
            "base_failure_reasons": loser["failure_reasons"],
            "comparison_failure_reasons": winner["failure_reasons"],
            "consistent_positive_yearly_effect": both_years,
            "next_action": ("PREREGISTER_A_NEW_COMPARISON" if stable
                            else "DO_NOT_PROMOTE_INCONSISTENT_TRAINING_CONTRAST"),
            "interpretation": "POST_HOC_TRAINING_ASSOCIATION_NOT_CAUSAL",
            "independent_oos_proven": False,
            "live_trading_authorized": False,
        })
    pairs.sort(key=lambda r: (
        -int(r["next_action"] == "PREREGISTER_A_NEW_COMPARISON"),
        -r["training_score_delta"], -r["training_net_delta_usd_per_oz"],
        r["changed_field"], r["base_formula_identity"],
        r["comparison_formula_identity"]))
    return {
        "schema": "NRFX_MATCHED_TRAINING_HYPOTHESES_V1",
        "training_years": list(years), "evaluated_formulas": len(evaluated),
        "total_single_parameter_pairs": len(pairs),
        "returned_pairs": len(pairs[:limit]),
        "contrasts": pairs[:limit],
        "interpretation": "DESCRIPTIVE_POST_HOC_TRAINING_ONLY",
        "independent_oos_proven": False, "live_trading_authorized": False,
    }
