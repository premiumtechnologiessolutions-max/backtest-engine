"""Synthetic tests for frozen strategy parameter provenance (no Gold data)."""
from copy import deepcopy

import pytest

from scripts.frozen_parameter_contract import verify_frozen_parameter_contract


def _parameters():
    return {
        "year": 2012,
        "strategy": "bos_fib_m1_frozen_h1_120m_no_dual_pivots",
        "bos_fib": {
            "pivot_left": 3, "pivot_right": 3, "fib_entry": 0.618,
            "zone_lower": 0.618, "zone_upper": 0.786,
            "reward_risk": 1.0, "sl_buffer_usd": 0.10,
            "min_break_usd": 0.10, "min_impulse_usd": 1.0,
            "expiry_minutes": 120, "max_bos_waves_per_regime": 2,
            "min_gross_reward_fee_multiple": 0.0,
            "all_in_cost_per_ounce": 0.40,
            "ignore_ambiguous_dual_pivots": True,
        },
        "h1": {
            "ema_span": 50, "slope_lag_bars": 5,
            "max_regime_age_minutes": 120,
        },
        "cost_per_oz_all_in": 0.40,
        "do_not_claim_clean_oos": True,
    }


def test_frozen_parameter_snapshot_accepted():
    verify_frozen_parameter_contract(_parameters(), year=2012)


@pytest.mark.parametrize("group,key,wrong", [
    ("bos_fib", "pivot_left", 4),
    ("bos_fib", "pivot_right", 2),
    ("bos_fib", "fib_entry", 0.62),
    ("bos_fib", "zone_lower", 0.5),
    ("bos_fib", "zone_upper", 0.87),
    ("bos_fib", "reward_risk", 2.0),
    ("bos_fib", "sl_buffer_usd", 0.20),
    ("bos_fib", "min_break_usd", 0.20),
    ("bos_fib", "min_impulse_usd", 2.0),
    ("bos_fib", "expiry_minutes", 90),
    ("bos_fib", "max_bos_waves_per_regime", 3),
    ("bos_fib", "min_gross_reward_fee_multiple", 5.0),
    ("bos_fib", "all_in_cost_per_ounce", 0.50),
    ("bos_fib", "ignore_ambiguous_dual_pivots", False),
    ("h1", "ema_span", 40),
    ("h1", "slope_lag_bars", 4),
    ("h1", "max_regime_age_minutes", None),
    ("h1", "max_regime_age_minutes", 180),
    ("bos_fib", "pivot_left", True),  # True == 1 must not bypass checks
    ("bos_fib", "reward_risk", 1),  # 1 == 1.0 must not bypass checks
    ("h1", "max_regime_age_minutes", 120.0),
    ("bos_fib", "fib_entry", float("nan")),
])
def test_nested_strategy_drift_rejected(group, key, wrong):
    params = _parameters()
    params[group][key] = wrong
    with pytest.raises(ValueError, match="Frozen"):
        verify_frozen_parameter_contract(params, year=2012)


@pytest.mark.parametrize("field,wrong", [
    ("year", 2013), ("year", True),
    ("strategy", "different_strategy"),
    ("cost_per_oz_all_in", 0.50),
    ("cost_per_oz_all_in", "0.40"),
    ("do_not_claim_clean_oos", False),
    ("do_not_claim_clean_oos", 1),
])
def test_outer_parameter_drift_rejected(field, wrong):
    params = _parameters()
    params[field] = wrong
    with pytest.raises(ValueError, match="Frozen"):
        verify_frozen_parameter_contract(params, year=2012)


@pytest.mark.parametrize("group", ["bos_fib", "h1"])
def test_missing_and_extra_nested_keys_rejected(group):
    params = _parameters()
    key = next(iter(params[group]))
    del params[group][key]
    with pytest.raises(ValueError, match="keys"):
        verify_frozen_parameter_contract(params, year=2012)
    params = _parameters()
    params[group]["new_default"] = 1
    with pytest.raises(ValueError, match="keys"):
        verify_frozen_parameter_contract(params, year=2012)


def test_missing_extra_outer_keys_and_wrong_types_rejected():
    for mutate in (
        lambda p: p.pop("bos_fib"),
        lambda p: p.update(unknown=1),
        lambda p: p.update(bos_fib=[]),
        lambda p: p.update(h1=None),
    ):
        params = _parameters()
        mutate(params)
        with pytest.raises(ValueError, match="Frozen"):
            verify_frozen_parameter_contract(params, year=2012)


@pytest.mark.parametrize("year", [True, 2012.0, 2009, 2027])
def test_invalid_expected_year_rejected(year):
    with pytest.raises(ValueError, match="integer source year"):
        verify_frozen_parameter_contract(_parameters(), year=year)
