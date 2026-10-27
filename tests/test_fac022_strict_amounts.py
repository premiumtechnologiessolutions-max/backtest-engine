"""FAC022 money comparisons must not pass on relative tolerance or nonfinite exports."""
import numpy as np
import pytest
from scripts.batch_m5_path_efficiency_grid import strict_amounts_match


def test_exactly_equal_and_tiny_roundoff_pass():
    assert strict_amounts_match([1_000_000., -12.], [1_000_000., -12.])
    assert strict_amounts_match(3.0, 3.0 + 5e-8)


def test_default_numpy_relative_tolerance_would_hide_material_drift():
    actual = np.array([1_000_000., 2_000_000.])
    altered = np.array([1_000_000.01, 2_000_000.02])
    assert np.allclose(actual, altered, atol=1e-7)  # unsafe default rtol
    assert not strict_amounts_match(actual, altered)


@pytest.mark.parametrize('left,right', [
    ([float('inf')], [float('inf')]),
    ([float('nan')], [float('nan')]),
    ([1.0], [float('nan')]),
    ([1.0, 2.0], [1.0]),
    ([1.0], ['not a number']),
    (float('inf'), float('inf')),
])
def test_invalid_or_mismatched_money_fails_closed(left, right):
    assert not strict_amounts_match(left, right)


def test_material_absolute_drift_fails_even_for_small_amounts():
    assert not strict_amounts_match(0.0, 1e-5)
    assert not strict_amounts_match(-20.2, -20.20001)
