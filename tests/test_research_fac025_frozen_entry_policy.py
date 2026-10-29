"""Synthetic preregistration tests; no Gold ZIP, backtests, or P/L."""
from datetime import datetime, timedelta, timezone
import copy

import pytest

from scripts.research_fac025_frozen_grid import frozen_specs
from scripts.research_fac025_frozen_entry_policy import (
    POLICY, POLICY_SHA256, frozen_policy_fingerprint, propose_frozen_entry,
)

UTC = timezone.utc
END = datetime(2026, 1, 5, 14, 15, tzinfo=UTC)
NOW = END + timedelta(seconds=1)
SPEC = frozen_specs()[0]


def rows(*, bullish=True, sweep=True):
    first = END - timedelta(minutes=195)
    out = []
    for i in range(195):
        opened = first + timedelta(minutes=i)
        hour = opened.hour
        if bullish:
            close = {11: 999.7, 12: 999.9, 13: 1000.0, 14: 1000.1}[hour]
        else:
            close = {11: 1000.3, 12: 1000.1, 13: 1000.0, 14: 999.9}[hour]
        high, low = close + 0.2, close - 0.2
        if sweep and i == 194:
            if bullish:
                low = 999.2
            else:
                high = 1000.8
        out.append({
            "open_at": opened,
            "bid_open": close, "bid_high": high,
            "bid_low": low, "bid_close": close,
            "ask_open": close + 0.1, "ask_high": high + 0.1,
            "ask_low": low + 0.1, "ask_close": close + 0.1,
            "bid_received_at": opened + timedelta(minutes=1),
            "ask_received_at": opened + timedelta(minutes=1),
        })
    return out


def evaluate(data):
    return propose_frozen_entry(NOW, data, [], spec_id=SPEC["id"],
                                parameters=SPEC["parameters"],
                                fingerprint=SPEC["fingerprint"])


def test_policy_is_exactly_frozen_one_hypothesis():
    assert frozen_policy_fingerprint() == POLICY_SHA256
    assert POLICY["capacity"] == 1 and POLICY["fee_usd_per_oz"] == "0.40"
    assert POLICY["max_entry_delay_seconds"] == 60


@pytest.mark.parametrize("bullish,side", [(True, "BUY"), (False, "SELL")])
def test_sweep_with_prior_complete_h1_emits_intent_not_fill(bullish, side):
    result = evaluate(rows(bullish=bullish))
    assert result["status"] == "RESEARCH_INTENT_ONLY"
    assert result["side"] == side
    assert result["entry_price"] == "N/A" and result["stop_price"] == "N/A"
    assert result["capacity_verified"] is False
    assert result["source_authenticated"] is False
    assert result["monthly_net_pnl_usd_per_oz"] == "N/A"
    assert result["risk_distance_usd_per_oz"] > 0
    assert result["target_distance_usd_per_oz"] > result["risk_distance_usd_per_oz"]


def test_no_sweep_is_no_intent():
    assert evaluate(rows(sweep=False))["status"] == "NO_INTENT"


def test_missing_h1_minute_blocks_even_if_recent_filter_window_complete():
    data = rows()
    del data[90]  # 12:30; outside last four M15, inside older H1 context
    result = evaluate(data)
    assert result["status"] == "NO_INTENT"
    assert result["reason"] == "INCOMPLETE_H1_CONTEXT"


def test_missing_last_m15_minute_never_fabricated():
    data = rows()
    del data[-3]
    assert evaluate(data)["reason"] == "INCOMPLETE_OBSERVED_M15"


def test_late_ask_receipt_rejected_before_any_intent():
    data = rows()
    data[-1]["ask_received_at"] = NOW
    with pytest.raises(ValueError, match="at/after signal"):
        evaluate(data)


def test_mutated_frozen_spec_rejected():
    changed = copy.deepcopy(SPEC["parameters"])
    changed["lookback"] = 16
    with pytest.raises(ValueError):
        propose_frozen_entry(NOW, rows(), [], spec_id=SPEC["id"],
                             parameters=changed, fingerprint=SPEC["fingerprint"])


def test_policy_sha_rejects_posthoc_mutation(monkeypatch):
    from scripts import research_fac025_frozen_entry_policy as module
    monkeypatch.setitem(module.POLICY, "reward_multiple", "3.00")
    with pytest.raises(ValueError, match="mutated"):
        module.frozen_policy_fingerprint()
