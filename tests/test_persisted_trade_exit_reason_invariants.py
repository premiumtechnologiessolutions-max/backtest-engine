"""Negative controls for frozen M1 limit exit-price/reason consistency.

Synthetic ledger pairs are deliberately identical and financially balanced:
the audit must reject impossible named fills without relying on parity alone.
These do not verify the existence of real broker prints.
"""
from __future__ import annotations

import io

import pandas as pd
import pytest

from norisk_quant.persisted_trade_integrity import verify_persisted_trade_ledger


def _matching_ledgers(reason: str, exit_price: float, *, side: int = 1):
    stop, target = (99.0, 102.0) if side == 1 else (101.0, 98.0)
    gross = side * (exit_price - 100.0)
    entry = pd.Timestamp("2024-03-04T10:01:00Z")
    executed = pd.DataFrame([{
        "strategy": "synthetic_bos",
        "signal_at": pd.Timestamp("2024-03-04T10:00:00Z"),
        "entry_at": entry,
        "closed_at": entry if reason == "entry_open_beyond_stop"
        else pd.Timestamp("2024-03-04T10:03:00Z"),
        "side": side,
        "entry_price": 100.0,
        "exit_price": exit_price,
        "stop": stop,
        "target": target,
        "ounces": 1.0,
        "gross_pnl": gross,
        "cost": 0.40,
        "net_pnl": gross - 0.40,
        "exit_reason": reason,
        "gap_minutes": 0,
    }])
    exported = pd.read_csv(io.StringIO(executed.to_csv(index=False)))
    return executed, exported


@pytest.mark.parametrize("reason,exit_price,side", [
    ("stop", 98.5, 1),
    ("ambiguous_stop_first", 102.0, 1),
    ("target", 101.5, 1),
    ("open_target", 101.5, 1),
    ("open_stop", 99.5, 1),
    ("gap_stop", 99.5, 1),
    ("entry_open_beyond_stop", 99.5, 1),
    ("stop", 101.5, -1),
    ("target", 98.5, -1),
    ("gap_stop", 100.5, -1),
])
def test_matching_financially_balanced_impossible_exit_is_rejected(
    reason, exit_price, side
):
    executed, exported = _matching_ledgers(reason, exit_price, side=side)
    with pytest.raises(ValueError, match="exit price differs|adverse open exit"):
        verify_persisted_trade_ledger(executed, exported)


def test_matching_unknown_exit_reason_is_rejected():
    executed, exported = _matching_ledgers("fabricated_fill", 102.0)
    with pytest.raises(ValueError, match="unknown exit reason"):
        verify_persisted_trade_ledger(executed, exported)


@pytest.mark.parametrize("reason,exit_price,side", [
    ("stop", 99.0, 1),
    ("ambiguous_stop_first", 99.0, 1),
    ("target", 102.0, 1),
    ("open_target", 102.0, 1),
    ("open_stop", 98.5, 1),
    ("gap_stop", 98.5, 1),
    ("entry_open_beyond_stop", 98.5, 1),
    ("end_of_data", 100.5, 1),
    ("stop", 101.0, -1),
    ("target", 98.0, -1),
    ("gap_stop", 102.0, -1),
])
def test_valid_synthetic_exit_contract_is_accepted(reason, exit_price, side):
    executed, exported = _matching_ledgers(reason, exit_price, side=side)
    verify_persisted_trade_ledger(executed, exported)
