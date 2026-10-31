"""Frozen H1/BOS integer settings must reject nonfinite and ambiguous types.

This is a regression guard for a NaN H1 age silently disabling the
predeclared stale-regime filter, and for NaN/Infinity wave limits.
"""
import numpy as np
import pytest

from norisk_quant.bos_fib import BosFibSettings
from norisk_quant.h1_regime import H1RegimeSettings


@pytest.mark.parametrize("field,minimum", [
    ("ema_span", 2),
    ("slope_lag_bars", 1),
])
@pytest.mark.parametrize("bad", [
    True, False, 5.0, float("nan"), float("inf"), "5",
])
def test_h1_integer_bar_parameters_fail_closed(field, minimum, bad):
    with pytest.raises(ValueError, match=field):
        H1RegimeSettings(**{field: bad})
    with pytest.raises(ValueError, match=field):
        H1RegimeSettings(**{field: minimum - 1})


@pytest.mark.parametrize("bad", [
    True, False, 120.0, 120.5, float("nan"), float("inf"), "120", -1,
])
def test_h1_freshness_age_rejects_noninteger_or_nonfinite(bad):
    with pytest.raises(ValueError, match="maximum age"):
        H1RegimeSettings(max_regime_age_minutes=bad)


@pytest.mark.parametrize("field", [
    "pivot_left", "pivot_right", "expiry_minutes",
    "max_bos_waves_per_regime",
])
@pytest.mark.parametrize("bad", [
    True, False, 3.0, float("nan"), float("inf"), "3", 0,
])
def test_bos_discrete_parameters_fail_closed(field, bad):
    with pytest.raises(ValueError, match=field):
        BosFibSettings(**{field: bad})


@pytest.mark.parametrize("bad", [1, 0, "False", None, np.bool_(True)])
def test_bos_dual_pivot_flag_requires_real_boolean(bad):
    with pytest.raises(ValueError, match="ignore_ambiguous_dual_pivots"):
        BosFibSettings(ignore_ambiguous_dual_pivots=bad)


def test_frozen_defaults_and_opt_in_120m_age_remain_unchanged():
    assert H1RegimeSettings() == H1RegimeSettings(ema_span=50, slope_lag_bars=5)
    assert H1RegimeSettings(max_regime_age_minutes=120).max_regime_age_minutes == 120
    assert H1RegimeSettings(max_regime_age_minutes=0).max_regime_age_minutes == 0
    assert BosFibSettings().ignore_ambiguous_dual_pivots is False
    assert BosFibSettings(ignore_ambiguous_dual_pivots=True).ignore_ambiguous_dual_pivots is True
    assert BosFibSettings().all_in_cost_per_ounce == 0.40


def test_numpy_integral_inputs_remain_valid_without_bool_coercion():
    h1 = H1RegimeSettings(
        ema_span=np.int64(50), slope_lag_bars=np.int64(5),
        max_regime_age_minutes=np.int64(120),
    )
    bos = BosFibSettings(
        pivot_left=np.int64(3), pivot_right=np.int64(3),
        expiry_minutes=np.int64(120), max_bos_waves_per_regime=np.int64(2),
    )
    assert h1.max_regime_age_minutes == 120
    assert bos.max_bos_waves_per_regime == 2
