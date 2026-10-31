"""Independent immutable parameter contract for the archived BOS/H1 replay.

Values are deliberately duplicated here rather than imported from strategy
defaults: a future change to a default must not silently relabel a new model
as the previously frozen experiment. This verifies recorded configuration,
not actual broker execution or source-archive identity.
"""
from __future__ import annotations


# Snapshot of the 2026-10-25 frozen strategy, independent of mutable defaults.
_FROZEN_BOS = {
    "pivot_left": 3,
    "pivot_right": 3,
    "fib_entry": 0.618,
    "zone_lower": 0.618,
    "zone_upper": 0.786,
    "reward_risk": 1,
    "sl_buffer_usd": 0.10,
    "min_break_usd": 0.10,
    "min_impulse_usd": 1.0,
    "expiry_minutes": 120,
    "max_bos_waves_per_regime": 2,
    "min_gross_reward_fee_multiple": 0.0,
    "all_in_cost_per_ounce": 0.40,
    "ignore_ambiguous_dual_pivots": True,
}
_FROZEN_H1 = {
    "ema_span": 50,
    "slope_lag_bars": 5,
    "max_regime_age_minutes": 120,
}
_STRATEGY = "bos_fib_m1_frozen_h1_120m_no_dual_pivots"


def _exact_mapping(observed: object, expected: dict, label: str) -> None:
    if type(observed) is not dict or set(observed) != set(expected):
        raise ValueError(f"Frozen {label} keys or type drifted")
    for key, reference in expected.items():
        actual = observed[key]
        # Python's True == 1 and 1 == 1.0 are not evidence of identical
        # parameter types; reject coercion and unfamiliar scalar wrappers.
        if type(actual) is not type(reference) or actual != reference:
            raise ValueError(f"Frozen {label}.{key} differs from preregistration")


def verify_frozen_parameter_contract(parameters: object, *, year: int) -> None:
    """Fail closed if a persisted annual run no longer matches frozen settings."""
    if type(year) is not int or not 2010 <= year <= 2026:
        raise ValueError("Frozen parameter contract requires an integer source year")
    expected = {
        "year": year,
        "strategy": _STRATEGY,
        "bos_fib": _FROZEN_BOS,
        "h1": _FROZEN_H1,
        "cost_per_oz_all_in": 0.40,
        "do_not_claim_clean_oos": True,
    }
    if type(parameters) is not dict or set(parameters) != set(expected):
        raise ValueError("Frozen run parameter schema drifted")
    for key in ("year", "strategy", "cost_per_oz_all_in",
                "do_not_claim_clean_oos"):
        actual, reference = parameters[key], expected[key]
        if type(actual) is not type(reference) or actual != reference:
            raise ValueError(f"Frozen run parameter {key} drifted")
    _exact_mapping(parameters["bos_fib"], _FROZEN_BOS, "BOS")
    _exact_mapping(parameters["h1"], _FROZEN_H1, "H1")
