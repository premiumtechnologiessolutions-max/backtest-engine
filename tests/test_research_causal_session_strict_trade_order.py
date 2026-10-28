"""FAC025 causal boundary tests: same-instant outcomes are not preknown.

Synthetic-only; no real Gold source, no portfolio or OOS claims.
"""
from datetime import datetime, timedelta, timezone

import pytest

from scripts.research_causal_session_risk import evaluate_causal_gate


def _sample():
    signal_at = datetime(2026, 1, 5, 13, 0, tzinfo=timezone.utc)
    bars = [
        {
            "end_at": signal_at - timedelta(minutes=15 * (3 - i)),
            "high": 101.0, "low": 99.0, "close": 100.0,
            "observed_m1_count": 15,
        }
        for i in range(4)
    ]
    # Completed M15 close must precede the decision instant.
    return signal_at + timedelta(seconds=1), bars


@pytest.mark.parametrize("net", [-10.0, 10.0, 0.0])
def test_same_instant_closed_trade_is_not_preknown(net):
    signal_at, bars = _sample()
    trades = [{"closed_at": signal_at, "net_usd_per_oz": net}]
    with pytest.raises(ValueError, match="same-instant"):
        evaluate_causal_gate(signal_at, bars, trades)


def test_microsecond_before_signal_is_causal_and_counts_net_loss():
    signal_at, bars = _sample()
    trades = [{
        "closed_at": signal_at - timedelta(microseconds=1),
        "net_usd_per_oz": -3.0,
    }]
    result = evaluate_causal_gate(signal_at, bars, trades)
    assert result["reason"] == "PREKNOWN_REALIZED_DAILY_LOSS_HALT"
    assert result["realized_today_usd_per_oz"] == -3.0


def test_future_closed_trade_is_rejected_even_when_profitable():
    signal_at, bars = _sample()
    trades = [{
        "closed_at": signal_at + timedelta(microseconds=1),
        "net_usd_per_oz": 100.0,
    }]
    with pytest.raises(ValueError, match="Future"):
        evaluate_causal_gate(signal_at, bars, trades)


def test_invalid_pnl_at_same_instant_still_rejected_as_nonfinite():
    signal_at, bars = _sample()
    trades = [{"closed_at": signal_at, "net_usd_per_oz": float("nan")}]
    with pytest.raises(ValueError, match="finite numeric"):
        evaluate_causal_gate(signal_at, bars, trades)


def test_prior_day_trade_is_not_part_of_current_ny_loss_halt():
    signal_at, bars = _sample()
    trades = [{
        "closed_at": signal_at - timedelta(days=1),
        "net_usd_per_oz": -100.0,
    }]
    result = evaluate_causal_gate(signal_at, bars, trades)
    assert result["status"] == "ELIGIBLE_RESEARCH_ONLY"
    assert result["realized_today_usd_per_oz"] == 0.0
