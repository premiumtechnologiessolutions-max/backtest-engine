"""Deterministic, training-only arithmetic research proposal generator.

This module proposes experiments; it does not fit orders, open holdout data,
claim a statistical edge, or authorize live trading. Every supplied candidate
must have complete reconciled training evidence before *any* ranking occurs.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import random
import re

from .math_discovery import Formula
from .research_training_integrity import training_summary

_SCHEMA = "NRFX_ARITHMETIC_EVOLUTION_V1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_METRICS = frozenset({"months", "net_usd_per_oz", "trades", "fees_usd",
                      "positive_months", "uncertain_gap_trades",
                      "synthetic_forced_closures", "accounting"})
_OPTIONS = {
    "lookback": (5, 8, 10, 12, 15, 20, 30, 45, 60, 90, 120, 180, 240),
    "feature_a": tuple(range(6)), "feature_b": tuple(range(6)),
    "feature_c": tuple(range(6)),
    "operator_ab": tuple(range(5)), "operator_c": tuple(range(5)),
    "reverse": (0, 1),
    "threshold": (.1, .2, .35, .5, .75, 1., 1.25, 1.5, 2., 3., 4.),
    "stop_usd": (1., 2., 3., 5., 8., 10., 15., 20., 30., 50.),
    "reward_risk": (.5, .75, 1., 1.25, 1.5, 2., 3., 4.),
    "cooldown": (1, 3, 5, 10, 15, 30, 60, 120, 240),
}


def _digest(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def _formula(raw: object) -> Formula:
    if type(raw) is not dict or set(raw) != set(Formula.__dataclass_fields__):
        raise ValueError("Each formula requires exactly the frozen grammar fields")
    try:
        validated = Formula(**raw)
        # The grammar accepts both 1 and 1.0 for continuous parameters.
        # They have identical trading semantics but distinct JSON digests;
        # normalize before deduplication, lineage, and evidence hashing.
        canonical = asdict(validated)
        for field in ("threshold", "stop_usd", "reward_risk"):
            canonical[field] = float(canonical[field])
        return Formula(**canonical)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid arithmetic formula") from exc


def _mutate(parent: Formula, rng: random.Random) -> tuple[Formula, list[str]]:
    values = asdict(parent)
    fields = list(_OPTIONS)
    changed = []
    for field in rng.sample(fields, k=2 if rng.randrange(5) == 0 else 1):
        choices = [v for v in _OPTIONS[field] if v != values[field]]
        values[field] = rng.choice(choices)
        changed.append(field)
    return Formula(**values), changed


def evolve_training_generation(candidates: list[dict], years: tuple[int, ...], *,
                               seed: int, generation: int,
                               proposal_count: int = 12,
                               explored_ids: tuple[str, ...] = ()) -> dict:
    """Create bounded, reproducible next-generation hypotheses from TRAINING only.

    candidates: [{"formula": all Formula fields,
                  "records": [{"year": YYYY, "metrics": reconciled year}, ...]}]
    All records MUST cover exactly ``years``; holdout/OOS fields are rejected.
    Returns an immutable-content SHA envelope, not a performance certificate.
    """
    if (type(seed) is not int or not 0 <= seed < 2**63
            or type(generation) is not int or not 0 <= generation <= 1_000_000
            or type(proposal_count) is not int or not 1 <= proposal_count <= 128
            or type(candidates) is not list or not 1 <= len(candidates) <= 128
            or type(explored_ids) is not tuple or len(explored_ids) > 100_000
            or any(type(x) is not str or not _HEX.fullmatch(x) for x in explored_ids)
            or len(set(explored_ids)) != len(explored_ids)):
        raise ValueError("Invalid bounded training evolution controls")
    seen = set(explored_ids)
    evaluated = {}
    for candidate in candidates:
        if type(candidate) is not dict or set(candidate) != {"formula", "records"}:
            raise ValueError("Only formula and complete training records are accepted")
        formula = _formula(candidate["formula"])
        identity = formula.identity()
        if identity in evaluated:
            raise ValueError("Duplicate evaluated formula")
        records = candidate["records"]
        if (type(records) is not list or any(
                type(r) is not dict or set(r) != {"year", "metrics"}
                or type(r["metrics"]) is not dict
                or set(r["metrics"]) != _METRICS for r in records)):
            raise ValueError("Unexpected or incomplete training record schema")
        # Fail closed on missing years, wrong fees, invalid months, and arithmetic.
        summary = training_summary(records, years, fee_per_trade=0.40)
        canonical_records = sorted(records, key=lambda r: r["year"])
        evaluated[identity] = (formula, summary, canonical_records)
        seen.add(identity)
    ranking = sorted(evaluated, key=lambda identity: (
        -evaluated[identity][1]["training_score"],
        -evaluated[identity][1]["net_usd_per_oz"], identity))
    source = {"schema": _SCHEMA, "training_years": list(years),
              "candidates": [{"identity": i, "formula": asdict(evaluated[i][0]),
                              "records": evaluated[i][2]} for i in sorted(evaluated)]}
    source_digest = _digest(source)
    rng = random.Random(seed + generation * 1_000_003)
    proposals = []
    # Bounded attempts: duplicates cannot produce infinite loops.
    for _ in range(proposal_count * 100):
        if len(proposals) == proposal_count:
            break
        # 60% exploit top training candidates; 40% explore the full universe.
        pool = ranking[:min(3, len(ranking))] if rng.random() < .6 else ranking
        parent_id = rng.choice(pool)
        child, changed = _mutate(evaluated[parent_id][0], rng)
        child_id = child.identity()
        if child_id in seen:
            continue
        seen.add(child_id)
        proposals.append({"identity": child_id, "parent_identity": parent_id,
                          "mutated_fields": changed, "formula": asdict(child)})
    if len(proposals) != proposal_count:
        raise ValueError("Mutation space exhausted under the frozen research budget")
    result = {"schema": _SCHEMA, "generation": generation, "seed": seed,
              "training_years": list(years), "training_evidence_sha256": source_digest,
              "rankings": [{"identity": i, "training_score": evaluated[i][1]["training_score"],
                            "training_screen": evaluated[i][1]["screen"],
                            "net_usd_per_oz": evaluated[i][1]["net_usd_per_oz"]}
                           for i in ranking],
              "proposals": proposals,
              "independent_oos_proven": False, "live_trading_authorized": False,
              "selection_authority": "TRAINING_ONLY_RESEARCH_PROPOSALS"}
    result["manifest_sha256"] = _digest(result)
    return result
