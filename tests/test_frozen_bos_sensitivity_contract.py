import pytest
from scripts.run_bos_fib_frozen_sensitivity import (
    EXECUTION_SETTINGS, H1_SETTINGS, SOURCE_SHA, YEARLY_SETTINGS,
    validate_year_selection,
)


def test_frozen_bos_sensitivity_configuration_cannot_silently_drift():
    assert YEARLY_SETTINGS.fib_entry == 0.618
    assert YEARLY_SETTINGS.reward_risk == 1
    assert YEARLY_SETTINGS.ignore_ambiguous_dual_pivots
    assert H1_SETTINGS.max_regime_age_minutes == 120
    assert H1_SETTINGS.ema_span == 50
    assert H1_SETTINGS.slope_lag_bars == 5
    assert EXECUTION_SETTINGS.ounces == 1.0
    assert EXECUTION_SETTINGS.roundtrip_cost_per_ounce == 0.40
    assert len(SOURCE_SHA) == 64


@pytest.mark.parametrize("years", [
    [], [2012, 2012], [2009], [2027], [2012, 2012, 2020],
])
def test_frozen_year_selection_rejects_duplicate_and_outside_source(years):
    with pytest.raises(ValueError):
        validate_year_selection(years)


def test_frozen_year_selection_accepts_separate_exposed_years():
    validate_year_selection([2012, 2017, 2020, 2024])
