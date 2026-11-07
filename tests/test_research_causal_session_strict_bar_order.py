"""FAC025 synthetic-only regression: same-instant M15 OHLC is not preknown."""
from datetime import datetime, timedelta, timezone

import pytest
from scripts.research_causal_session_risk import evaluate_causal_gate

END = datetime(2026, 1, 5, 13, 0, tzinfo=timezone.utc)

def _bars():
    return [
        {"end_at": END - timedelta(minutes=15 * (3 - i)),
         "high": 101.0, "low": 99.0, "close": 100.0,
         "observed_m1_count": 15}
        for i in range(4)
    ]

@pytest.mark.parametrize("delta,match", [
    (timedelta(microseconds=-1), "Future"),
    (timedelta(0), "same-instant"),
])
def test_m15_close_not_preknown_at_or_after_signal(delta, match):
    with pytest.raises(ValueError, match=match):
        evaluate_causal_gate(END + delta, _bars(), [])

@pytest.mark.parametrize("delta", [
    timedelta(microseconds=1), timedelta(seconds=1), timedelta(seconds=60),
])
def test_preknown_m15_close_eligible_within_60_seconds(delta):
    result = evaluate_causal_gate(END + delta, _bars(), [])
    assert result["status"] == "ELIGIBLE_RESEARCH_ONLY"
    assert result["execution"] == "RESEARCH_GATE_ONLY_NO_ORDER"

def test_completed_bar_over_60_seconds_old_is_stale():
    result = evaluate_causal_gate(
        END + timedelta(seconds=60, microseconds=1), _bars(), [])
    assert result["reason"] == "STALE_COMPLETED_M15_CONTEXT"

def test_same_instant_m15_rejected_even_when_realized_loss_halts():
    trades = [{"closed_at": END - timedelta(minutes=1),
               "net_usd_per_oz": -100.0}]
    with pytest.raises(ValueError, match="same-instant"):
        evaluate_causal_gate(END, _bars(), trades)

def test_future_m15_rejected_even_outside_session():
    with pytest.raises(ValueError, match="Future"):
        evaluate_causal_gate(END - timedelta(hours=3, microseconds=1),
                             _bars(), [])
