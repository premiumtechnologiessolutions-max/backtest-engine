import pandas as pd
import pytest

from norisk_quant.model import Signal


@pytest.mark.parametrize("timestamp", [
    "2024-01-02T00:01:00",  # missing explicit offset
    pd.Timestamp("2024-01-02T00:01:00"),
    pd.NaT,
])
def test_signal_timestamp_requires_non_missing_timezone(timestamp):
    with pytest.raises(ValueError, match="explicit timezone"):
        Signal(timestamp, 1, 1.0, 2.0, "manual")


def test_signal_timestamp_accepts_utc_and_explicit_offset():
    for at in (
        pd.Timestamp("2024-01-02T00:01:00Z"),
        pd.Timestamp("2024-01-02T02:01:00+02:00"),
    ):
        s = Signal(at, 1, 1.0, 2.0, "manual")
        assert pd.Timestamp(s.confirmed_at).tzinfo is not None
