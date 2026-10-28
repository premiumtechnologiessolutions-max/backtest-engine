"""Synthetic causal controls for FAC025; no XAUUSD backtest claims."""
from datetime import datetime, timedelta, timezone
import pytest
from scripts.research_causal_session_risk import evaluate_causal_gate

UTC = timezone.utc


def context(month=1, day=5, hour=13):
    now = datetime(2026, month, day, hour, 0, tzinfo=UTC)
    bars = [
        {"end_at": now - timedelta(minutes=15 * (3 - i)),
         "high": 101.0, "low": 99.0, "close": 100.0,
         "observed_m1_count": 15}
        for i in range(4)
    ]
    return now, bars


def gate(now, bars, trades=None, **kwargs):
    return evaluate_causal_gate(now, bars, trades or [], **kwargs)


def test_winter_ny_session_eligible():
    now, bars = context()
    result = gate(now, bars)
    assert result["status"] == "ELIGIBLE_RESEARCH_ONLY"
    assert result["range_ratio"] == pytest.approx(.02)
    assert result["execution"] == "RESEARCH_GATE_ONLY_NO_ORDER"


def test_summer_dst_session_eligible_at_12utc():
    now, bars = context(month=7, hour=12)
    assert gate(now, bars)["status"] == "ELIGIBLE_RESEARCH_ONLY"


def test_summer_13utc_also_in_session_but_11utc_outside():
    now, bars = context(month=7, hour=11)
    assert gate(now, bars)["reason"] == "OUTSIDE_FROZEN_NY_SESSION"


def test_closed_trade_loss_halt_uses_only_net_after_cost():
    now, bars = context()
    trades = [{"closed_at": now - timedelta(minutes=1), "net_usd_per_oz": -3.0}]
    assert gate(now, bars, trades)["reason"] == "PREKNOWN_REALIZED_DAILY_LOSS_HALT"


def test_previous_new_york_day_does_not_trigger_halt():
    now, bars = context()
    trades = [{"closed_at": now - timedelta(days=1), "net_usd_per_oz": -100.0}]
    assert gate(now, bars, trades)["status"] == "ELIGIBLE_RESEARCH_ONLY"


def test_closed_profitable_trade_offsets_loss_before_signal():
    now, bars = context()
    trades = [
        {"closed_at": now - timedelta(minutes=3), "net_usd_per_oz": -3.5},
        {"closed_at": now - timedelta(minutes=1), "net_usd_per_oz": 1.0},
    ]
    assert gate(now, bars, trades)["status"] == "ELIGIBLE_RESEARCH_ONLY"


def test_market_gap_blocks_without_fabricating_m15():
    now, bars = context()
    bars[1]["end_at"] -= timedelta(minutes=1)
    with pytest.raises(ValueError, match="quarter-hour"):
        gate(now, bars)
    now, bars = context()
    bars[0]["end_at"] -= timedelta(minutes=15)
    assert gate(now, bars)["reason"] == "MARKET_GAP_NO_SYNTHETIC_BARS"


def test_incomplete_m1_blocks():
    now, bars = context()
    bars[0]["observed_m1_count"] = 14
    assert gate(now, bars)["reason"] == "INCOMPLETE_OBSERVED_M15"


def test_stale_completed_bar_blocks():
    now, bars = context()
    assert gate(now + timedelta(minutes=2), bars)["reason"] == "STALE_COMPLETED_M15_CONTEXT"


def test_too_few_bars_blocks():
    now, bars = context()
    assert gate(now, bars[:2])["reason"] == "INSUFFICIENT_OBSERVED_M15"


@pytest.mark.parametrize("field", ["end_at", "closed_at"])
def test_future_observation_never_accepted(field):
    now, bars = context()
    if field == "end_at":
        bars.append({**bars[-1], "end_at": now + timedelta(minutes=15)})
        with pytest.raises(ValueError, match="Future"):
            gate(now, bars)
    else:
        trades = [{"closed_at": now + timedelta(seconds=1), "net_usd_per_oz": -1.0}]
        with pytest.raises(ValueError, match="Future"):
            gate(now, bars, trades)


def test_volatility_range_blocks_both_sides():
    now, bars = context()
    assert gate(now, bars, min_range_ratio=.021)["reason"] == "OUTSIDE_FROZEN_VOLATILITY_REGIME"
    assert gate(now, bars, max_range_ratio=.019)["reason"] == "OUTSIDE_FROZEN_VOLATILITY_REGIME"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "2"])
def test_invalid_pnl_fails_closed(bad):
    now, bars = context()
    trades = [{"closed_at": now, "net_usd_per_oz": bad}]
    with pytest.raises(ValueError, match="finite numeric"):
        gate(now, bars, trades)


def test_non_utc_timestamp_fails_closed():
    now, bars = context()
    with pytest.raises(ValueError, match="UTC-aware"):
        gate(now.replace(tzinfo=None), bars)


def test_out_of_order_bars_fails_closed():
    now, bars = context()
    with pytest.raises(ValueError, match="out-of-order"):
        gate(now, [bars[1], bars[0], bars[2], bars[3]])


def test_bars_must_be_real_complete_m1_not_boolean():
    now, bars = context()
    bars[2]["observed_m1_count"] = True
    with pytest.raises(ValueError, match="M1 count"):
        gate(now, bars)
