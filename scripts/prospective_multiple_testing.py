"""Pre-registered family-wise multiple-testing gate for *externally valid* p-values.

This is a statistical utility, NOT a backtest, p-value estimator or OOS
certification. Historical strategy search cannot supply valid confirmatory
p-values merely by calling this function.
"""
from __future__ import annotations

import math


def holm_bonferroni(p_values: dict[str, float], alpha: float = 0.05, *, registered_ids: frozenset[str] | None = None) -> dict[str, dict[str, float | bool]]:
    """Holm step-down FWER adjustment, deterministic ties, no missing trials.

    Caller must register the complete independent hypothesis family in advance.
    Each p-value must already be valid under its null; correlated parameter
    variants are not automatically independent hypotheses. Pass registered_ids
    to fail closed on omitted or unregistered hypotheses before correction.
    """
    if type(alpha) is not float or not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be a finite float strictly between zero and one")
    if not isinstance(p_values, dict) or not p_values:
        raise ValueError("complete nonempty hypothesis family required")
    for key, p in p_values.items():
        if not isinstance(key, str) or not key or type(p) is not float or not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError("invalid hypothesis identifier or p-value")
    if registered_ids is not None:
        if (type(registered_ids) is not frozenset or not registered_ids
                or any(type(name) is not str or not name for name in registered_ids)
                or set(p_values) != registered_ids):
            raise ValueError("observed hypothesis family differs from preregistered identities")
    ordered = sorted(p_values.items(), key=lambda pair: (pair[1], pair[0]))
    count = len(ordered)
    adjusted = {}
    running = 0.0
    for index, (name, p) in enumerate(ordered):
        running = min(1.0, max(running, (count - index) * p))
        adjusted[name] = {"raw_p": p, "holm_adjusted_p": running, "reject": running <= alpha}
    return {name: adjusted[name] for name in sorted(adjusted)}
