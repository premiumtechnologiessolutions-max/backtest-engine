"""Additional safety contracts for the research-only BID/ASK sweep simulator.

These tests use synthetic quotes only; they do not establish historical edge.
"""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import pytest

path = Path(__file__).resolve().parents[1] / "scripts" / "simulate_sweep_bid_ask_research.py"
spec = importlib.util.spec_from_file_location("sweep_fill_research_safety", path)
sim = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sim
spec.loader.exec_module(sim)

T = datetime(2026, 10, 30, tzinfo=timezone.utc)

class Signal:
    side = "BUY"
    confirmed_at = T
    extreme = 98.0

def quote(i, *, bid=100.0, spread=0.2):
    return sim.QuoteBar(
        T + timedelta(minutes=i),
        bid, bid + 0.1, bid - 0.1, bid,
        bid + spread, bid + spread + 0.1, bid + spread - 0.1, bid + spread,
    )

def test_time_exit_uses_bid_open_and_fee_once():
    result = sim.simulate_signal(Signal(), [quote(0), quote(1), quote(2)], max_hold_minutes=2)
    assert result.reason == "TIME_OPEN"
    assert result.exit_time == T + timedelta(minutes=2)
    assert result.exit == 100.0
    assert result.net_per_ounce == pytest.approx(result.gross_per_ounce - 0.40)

def test_missing_first_executable_minute_is_not_backfilled():
    assert sim.simulate_signal(Signal(), [quote(-1), quote(1)]) is None

def test_unclosed_position_is_not_reported_as_profit():
    assert sim.simulate_signal(Signal(), [quote(0), quote(1)], max_hold_minutes=5) is None

@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, "98", 0, -1])
def test_invalid_signal_extreme_is_rejected(bad):
    signal = Signal()
    signal.extreme = bad
    with pytest.raises(ValueError, match="extreme"):
        sim.simulate_signal(signal, [quote(0)])

def test_negative_target_is_not_a_valid_price():
    signal = Signal()
    signal.side = "SELL"
    signal.extreme = 200.0
    # A 1R short from 100 with stop at 200.1 implies a negative target.
    assert sim.simulate_signal(signal, [quote(0)]) is None
