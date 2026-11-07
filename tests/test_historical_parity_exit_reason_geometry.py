"""Synthetic exit-fill invariants for exact 13-field archived BOS/H1 replay.

These are *independent accounting checks*, not broker tick validation.
The two ledgers are deliberately modified identically to prove that
13/13 field equality alone cannot certify impossible exit executions.
"""
import pandas as pd
import pytest

from scripts.verify_bos_h1_parity import exact_ledger_check


def matching_trade(*, side=1, entry=100.0, stop=99.0, target=102.0,
                   exit_price=102.0, reason="target"):
    signal = pd.Timestamp("2024-01-02T00:01:00Z")
    opened = pd.Timestamp("2024-01-02T00:02:00Z")
    closed = pd.Timestamp("2024-01-02T00:03:00Z")
    gross = side * (exit_price - entry)
    actual = pd.DataFrame([{
        "signal_at": signal, "entry_at": opened, "closed_at": closed,
        "side": side, "entry_price": entry, "exit_price": exit_price,
        "stop": stop, "target": target, "gross_pnl": gross,
        "cost": 0.40, "net_pnl": gross - 0.40,
        "exit_reason": reason, "gap_minutes": 0,
    }])
    archived = pd.DataFrame([{
        "signal_time": int(signal.timestamp()),
        "entry_time": int(opened.timestamp()),
        "exit_time": int(closed.timestamp()),
        "side": side, "entry": entry, "exit": exit_price,
        "stop": stop, "target": target, "gross": gross,
        "fee": 0.40, "net": gross - 0.40,
        "exit_reason": reason, "gap_minutes": 0,
    }])
    return actual, archived


@pytest.mark.parametrize("reason,exit_price", [
    ("target", 101.0),
    ("open_target", 101.0),
    ("stop", 98.5),
    ("ambiguous_stop_first", 98.5),
    ("gap_stop", 99.5),
    ("open_stop", 99.5),
    ("entry_open_beyond_stop", 99.5),
    ("broker_override", 102.0),
])
def test_identically_corrupted_exit_labels_cannot_pass_replay(reason, exit_price):
    current, reference = matching_trade(reason=reason, exit_price=exit_price)
    with pytest.raises(AssertionError, match="Ledger invariant:"):
        exact_ledger_check(current, reference)


@pytest.mark.parametrize("reason,exit_price", [
    ("target", 102.0),
    ("open_target", 102.0),
    ("stop", 99.0),
    ("ambiguous_stop_first", 99.0),
    ("gap_stop", 98.5),
    ("open_stop", 98.5),
    ("entry_open_beyond_stop", 98.5),
    ("end_of_data", 101.0),
])
def test_valid_conservative_long_exit_reasons_pass(reason, exit_price):
    current, reference = matching_trade(reason=reason, exit_price=exit_price)
    assert exact_ledger_check(current, reference)["trades"] == 1


@pytest.mark.parametrize("reason,exit_price", [
    ("target", 100.0),
    ("open_target", 100.0),
    ("stop", 103.0),
    ("ambiguous_stop_first", 103.0),
    ("gap_stop", 103.5),
    ("open_stop", 103.5),
    ("entry_open_beyond_stop", 103.5),
    ("end_of_data", 101.0),
])
def test_valid_conservative_short_exit_reasons_pass(reason, exit_price):
    current, reference = matching_trade(
        side=-1, entry=102.0, stop=103.0, target=100.0,
        exit_price=exit_price, reason=reason,
    )
    assert exact_ledger_check(current, reference)["trades"] == 1


@pytest.mark.parametrize("reason,exit_price", [
    ("gap_stop", 102.5),
    ("open_stop", 102.5),
    ("entry_open_beyond_stop", 102.5),
])
def test_matching_favorable_short_stop_gap_is_rejected(reason, exit_price):
    current, reference = matching_trade(
        side=-1, entry=102.0, stop=103.0, target=100.0,
        exit_price=exit_price, reason=reason,
    )
    with pytest.raises(AssertionError, match="favorable price on adverse open stop"):
        exact_ledger_check(current, reference)
