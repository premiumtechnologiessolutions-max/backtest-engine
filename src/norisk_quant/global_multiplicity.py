"""Global strategy-search multiplicity diagnostics across frozen DAG shards.

Pure math only. P-value validity is NOT established by this module. Applied
corrections are descriptive under their stated assumptions and NEVER certify
a discovered edge or grant permission to run an actual market study.
"""
from __future__ import annotations

import hashlib
import json
import math

from norisk_quant.campaign_sharding import verify_sharded_campaign

SCHEMA = "NRFX_GLOBAL_STRATEGY_MULTIPLICITY_DIAGNOSTIC_V1"


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("ascii")).hexdigest()


def _ratio(value: object) -> tuple[int, int]:
    if (type(value) not in (tuple, list) or len(value) != 2
            or type(value[0]) is not int or type(value[1]) is not int):
        raise ValueError("Frozen p-values require exact integer numerator/denominator")
    numerator, denominator = value
    if not (0 <= numerator <= denominator <= 1_000_000_000
            and denominator >= 1):
        raise ValueError("Invalid bounded exact p-value fraction")
    return numerator, denominator


def global_adjusted_diagnostics(
    campaign: dict, exact_p_fractions: dict,
    *, alpha: float = 0.05, method: str = "benjamini_yekutieli",
) -> dict:
    """Evaluate a COMPLETE preregistered candidate family, never a subset.

    Benjamini-Yekutieli controls FDR with arbitrary dependence *if the input
    p-values are valid*. Bonferroni controls familywise error on the same
    assumption. That assumption and preregistration have to be evidenced
    OUTSIDE this function. Never label a rejection as a profitable strategy.
    """
    frozen = verify_sharded_campaign(campaign)
    if (type(exact_p_fractions) is not dict
            or type(method) is not str
            or method not in {"benjamini_yekutieli", "bonferroni"}
            or type(alpha) not in (int, float)
            or not math.isfinite(alpha) or not 0 < alpha < 1):
        raise ValueError("Invalid global multiplicity diagnostic policy")
    universe = sorted(item["id"]
                      for item in frozen["normalized_global_spec"]["strategies"])
    if set(exact_p_fractions) != set(universe):
        raise ValueError("All frozen candidates, including failures, are required")
    raw = {candidate: _ratio(exact_p_fractions[candidate])
           for candidate in universe}
    values = [(candidate, numerator / denominator)
              for candidate, (numerator, denominator) in raw.items()]
    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    m = len(ordered)
    harmonic = math.fsum(1 / k for k in range(1, m + 1))
    adjusted: dict[str, float] = {}
    if method == "bonferroni":
        for candidate, pvalue in ordered:
            adjusted[candidate] = min(1.0, m * pvalue)
    else:
        # Step-up adjusted BY values are a monotone right-to-left minimum.
        running = 1.0
        for rank in range(m, 0, -1):
            candidate, pvalue = ordered[rank - 1]
            running = min(running, m * harmonic * pvalue / rank)
            adjusted[candidate] = min(1.0, running)
    results = {}
    for candidate in universe:
        num, den = raw[candidate]
        results[candidate] = {
            "input_fraction": [num, den],
            "unadjusted_nominal_p": num / den,
            "adjusted_nominal_p": adjusted[candidate],
            "below_nominal_adjusted_alpha": adjusted[candidate] <= alpha,
            "independent_out_of_sample_verified": False,
            "strategy_approved": False,
        }
    body = {
        "schema": SCHEMA,
        "sharded_blueprint_sha256": frozen["sharded_blueprint_sha256"],
        "candidate_count": m,
        "shard_count": frozen["shard_count"],
        "correction_method": method,
        "alpha": float(alpha),
        "harmonic_correction": harmonic if method == "benjamini_yekutieli" else None,
        "results": results,
        "assumptions": (
            "Requires valid p-values and a genuinely frozen complete family. "
            "The diagnostic does NOT verify test validity, market provenance, "
            "selection independence, preregistration or an actual edge."
        ),
        "calculated_from_supplied_fractions_only": True,
        "market_data_opened": False,
        "execution_authorized": False,
        "trade_signals_generated": False,
        "research_results_accepted": False,
        "independent_oos_proven": False,
    }
    return {**body, "diagnostic_sha256": _digest(body)}
