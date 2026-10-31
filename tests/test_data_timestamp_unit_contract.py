"""M1 source identity and validation must not depend on Pandas timestamp storage unit.

Pandas 2.x DatetimeIndex.asi8 is expressed in the index's unit, which can
be seconds, milliseconds, microseconds or nanoseconds. SHA provenance and
minute-open checks must operate on UTC nanoseconds, regardless of storage.
These are synthetic quote fixtures, not original XAUUSD or OOS evidence.
"""
import pandas as pd
import pytest

from norisk_quant.data import (
    fingerprint_loaded_m1, normalize, validate_loaded_m1,
)


def _quotes() -> pd.DataFrame:
    base = 1704153600  # 2024-01-02 00:00 UTC
    rows = []
    for i in range(3):
        bid = 2000.0 + i
        rows.append({
            "ts": base + i * 60,
            "o": bid, "h": bid + 1.0, "l": bid - 1.0, "c": bid + .25,
            "ao": bid + .4, "ah": bid + 1.4,
            "al": bid - .6, "ac": bid + .65,
        })
    return normalize(pd.DataFrame(rows))


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_validated_m1_and_fingerprint_are_storage_unit_invariant(unit):
    baseline = _quotes()
    candidate = baseline.copy()
    candidate.index = candidate.index.as_unit(unit)
    assert candidate.index.unit == unit
    assert validate_loaded_m1(candidate) is candidate
    assert fingerprint_loaded_m1(candidate) == fingerprint_loaded_m1(baseline)


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_nonminute_m1_timestamp_rejected_regardless_of_storage_unit(unit):
    candidate = _quotes()
    candidate.index = (candidate.index + pd.Timedelta(seconds=1)).as_unit(unit)
    with pytest.raises(ValueError, match="minute opens"):
        validate_loaded_m1(candidate)
    with pytest.raises(ValueError, match="minute opens"):
        fingerprint_loaded_m1(candidate)


def test_second_storage_is_not_mistaken_for_nanoseconds_in_provenance():
    candidate = _quotes()
    candidate.index = candidate.index.as_unit("s")
    assert candidate.index.asi8[0] < 60_000_000_000
    # Previously the raw seconds would be hashed as if they were ns.
    assert fingerprint_loaded_m1(candidate) == fingerprint_loaded_m1(_quotes())
