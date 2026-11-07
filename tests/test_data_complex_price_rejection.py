"""Regression tests for audit F-05: complex prices must never be silently cast.

Only synthetic BID/ASK candles. No external data, brokers, or credentials.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from norisk_quant.data import (
    fingerprint_loaded_m1,
    normalize,
    quality,
    validate_loaded_m1,
)


def _rows():
    return [
        {"ts": 1704153600, "o": 2000.0, "h": 2001.0, "l": 1999.0,
         "c": 2000.5, "ao": 2000.4, "ah": 2001.4,
         "al": 1999.4, "ac": 2000.9},
        {"ts": 1704153660, "o": 2000.5, "h": 2002.0, "l": 2000.0,
         "c": 2001.0, "ao": 2000.9, "ah": 2002.4,
         "al": 2000.4, "ac": 2001.4},
    ]


@pytest.mark.parametrize("column", ["ts", "o", "ac"])
@pytest.mark.parametrize("imaginary", [0.0, 1.25])
def test_source_rejects_complex_cells_even_when_imaginary_zero(column, imaginary):
    rows = _rows()
    rows[0][column] = complex(rows[0][column], imaginary)
    with pytest.raises(ValueError, match="complex"):
        normalize(pd.DataFrame(rows))


def test_source_rejects_complex_hidden_in_object_column():
    raw = pd.DataFrame(_rows())
    raw["ac"] = raw["ac"].astype(object)
    raw.at[0, "ac"] = np.complex128(2000.9 + 0.01j)
    with pytest.raises(ValueError, match="complex"):
        normalize(raw, strict=False)


@pytest.mark.parametrize("gate", [
    validate_loaded_m1, fingerprint_loaded_m1, quality,
])
def test_public_data_gates_reject_complex_before_coercion(gate):
    valid = normalize(pd.DataFrame(_rows()))
    bad = valid.copy()
    bad["o"] = bad["o"].astype(np.complex128) + 0.05j
    with pytest.raises(ValueError, match="numeric non-boolean"):
        gate(bad)


def test_real_data_remains_accepted_and_fingerprint_is_stable():
    valid = normalize(pd.DataFrame(_rows()))
    validate_loaded_m1(valid)
    assert quality(valid)["rows"] == 2
    assert fingerprint_loaded_m1(valid) == fingerprint_loaded_m1(valid.copy())
