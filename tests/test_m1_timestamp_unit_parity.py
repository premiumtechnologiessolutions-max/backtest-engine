"""Regression: pandas DatetimeIndex.asi8 is not always nanoseconds.

Pandas 2.x can store UTC DatetimeIndex values in s/ms/us units, including
after CSV/Parquet reconstruction. All such indexes represent identical
minute-open instants and must produce identical canonical ledgers.
"""
import pandas as pd
import pytest

from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings, Signal
from norisk_quant.accounting import validate_execution


def _quotes(unit: str) -> pd.DataFrame:
    stamps = pd.to_datetime([
        "2024-07-17T13:00:00Z",
        "2024-07-17T13:01:00Z",
        "2024-07-17T13:02:00Z",
        "2024-07-17T13:20:00Z",
        "2024-07-17T13:21:00Z",
    ], utc=True).as_unit(unit)
    return pd.DataFrame({
        "o": [100., 100., 100., 97., 97.],
        "h": [100., 100., 100., 97., 97.],
        "l": [100., 100., 100., 97., 97.],
        "c": [100., 100., 100., 97., 97.],
    }, index=stamps)


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
@pytest.mark.parametrize("confirmed", [
    "2024-07-17T13:01:00Z",
    "2024-07-17T13:01:00.500Z",
])
def test_m1_storage_unit_does_not_change_execution_or_causality(unit, confirmed):
    bars = _quotes(unit)
    assert bars.index.unit == unit
    signal = Signal(pd.Timestamp(confirmed), 1, 1., 2., "unit_contract")
    settings = Settings(ounces=1, roundtrip_cost_per_ounce=.40)
    reference = run(bars, [signal], settings)
    optimized = run_fast(bars, [signal], settings)
    baseline = run(_quotes("ns"), [signal], settings)

    pd.testing.assert_frame_equal(reference.trades, baseline.trades)
    pd.testing.assert_frame_equal(reference.equity, baseline.equity)
    pd.testing.assert_frame_equal(optimized.trades, baseline.trades)
    pd.testing.assert_frame_equal(optimized.equity, baseline.equity)
    assert reference.equity.index.unit == optimized.equity.index.unit == "ns"
    assert reference.trades.iloc[0]["exit_reason"] == "gap_stop"
    assert reference.trades.iloc[0]["gap_minutes"] == 17
    assert reference.trades.iloc[0]["net_pnl"] == pytest.approx(-3.40)
    expected_entry = pd.Timestamp(
        "2024-07-17T13:02:00Z" if ".500" in confirmed
        else "2024-07-17T13:01:00Z"
    )
    assert reference.trades.iloc[0]["entry_at"] == expected_entry
    assert validate_execution(reference, settings)["accounting_checks"] == "PASSED"
    assert validate_execution(optimized, settings)["accounting_checks"] == "PASSED"


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_nonminute_timestamps_still_rejected_for_every_storage_unit(unit):
    bars = _quotes(unit)
    bars.index = bars.index + pd.Timedelta(seconds=1)
    for engine in (run, run_fast):
        with pytest.raises(ValueError, match="minute boundaries"):
            engine(bars, [], Settings())


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_storage_unit_does_not_change_stale_signal_expiry(unit):
    bars = _quotes(unit).iloc[[0, 3, 4]]
    signal = Signal(pd.Timestamp("2024-07-17T13:01:00.500Z"), 1, 1, 2)
    settings = Settings(max_entry_delay_minutes=1)
    reference = run(bars, [signal], settings)
    optimized = run_fast(bars, [signal], settings)
    assert reference.trades.empty and optimized.trades.empty
    assert reference.expired_signals == optimized.expired_signals == 1
    assert reference.pending_at_end == optimized.pending_at_end == 0
    pd.testing.assert_frame_equal(reference.equity, optimized.equity)
