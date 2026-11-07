import pandas as pd
import pytest

from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings, Signal
from norisk_quant.strategies_native import donchian_breakout_signals


def minutes():
    # Price crosses stop and target in one M1 bar; later gaps across stops.
    return pd.DataFrame(
        [
            {"o": 100., "h": 100., "l": 100., "c": 100.},
            {"o": 100., "h": 102., "l": 99.5, "c": 101.},
            {"o": 101., "h": 103., "l": 98., "c": 100.},
            {"o": 100., "h": 100., "l": 100., "c": 100.},
            {"o": 97., "h": 99., "l": 97., "c": 98.},
            {"o": 98., "h": 99., "l": 98., "c": 98.},
        ],
        index=pd.to_datetime(
            [
                "2024-07-17T13:00:00Z",
                "2024-07-17T13:01:00Z",
                "2024-07-17T13:02:00Z",
                "2024-07-17T13:03:00Z",
                "2024-07-17T13:20:00Z",
                "2024-07-17T13:21:00Z",
            ], utc=True,
        ),
    )


def test_fast_and_reference_execution_exact_same_trades_and_equity():
    bars = minutes()
    signals = [
        Signal(pd.Timestamp("2024-07-17T13:01:00Z"), 1, 1, 2, "fixture"),
        Signal(pd.Timestamp("2024-07-17T13:03:00Z"), 1, 1, 2, "fixture"),
    ]
    config = Settings(ounces=2, roundtrip_cost_per_ounce=0.40)
    baseline = run(bars, signals, config)
    fast = run_fast(bars, signals, config)
    pd.testing.assert_frame_equal(fast.trades, baseline.trades, check_dtype=False)
    pd.testing.assert_frame_equal(fast.equity, baseline.equity, check_dtype=False)
    assert fast.expired_signals == baseline.expired_signals
    assert fast.pending_at_end == baseline.pending_at_end


def test_flat_trade_fee_exact_and_gap_held_open():
    bars = minutes()
    sigs = [Signal(pd.Timestamp("2024-07-17T13:03:00Z"), 1, 1, 2, "fixture")]
    result = run_fast(bars, sigs, Settings())
    assert len(result.trades) == 1
    row = result.trades.iloc[0]
    assert row["cost"] == pytest.approx(0.4)
    assert row["exit_reason"] == "gap_stop"
    assert row["gap_minutes"] == 16
    assert row["net_pnl"] == pytest.approx(-3.4)


def test_donchian_requires_prior_completed_channel_and_next_bar():
    times = pd.date_range("2024-07-17T00:00:00Z", periods=240, freq="min")
    bars = pd.DataFrame(
        {"o": [100.] * 240, "h": [100.] * 240,
         "l": [100.] * 240, "c": [100.] * 240}, index=times
    )
    bars.loc[times[-60:], ["h", "c"]] = 105.
    signals = donchian_breakout_signals(
        bars, timeframe="H1", lookback=3, stop_distance=2, target_distance=4
    )
    assert len(signals) == 1
    assert signals[0].confirmed_at == pd.Timestamp("2024-07-17T04:00:00Z")
    assert signals[0].side == 1
    assert signals[0].target_distance == 4
