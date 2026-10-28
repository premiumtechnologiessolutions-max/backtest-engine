"""Synthetic negative controls: matching corrupt ledgers must not certify P/L."""

import io

import pandas as pd
import pytest

from norisk_quant.persisted_trade_integrity import verify_persisted_trade_ledger


def ledgers():
    raw = pd.DataFrame([{
        "strategy": "bos",
        "signal_at": pd.Timestamp("2024-01-01T00:00:00Z"),
        "entry_at": pd.Timestamp("2024-01-01T00:01:00Z"),
        "closed_at": pd.Timestamp("2024-01-01T00:03:00Z"),
        "side": 1,
        "entry_price": 100.0,
        "exit_price": 102.0,
        "stop": 99.0,
        "target": 102.0,
        "ounces": 1.0,
        "gross_pnl": 2.0,
        "cost": 0.40,
        "net_pnl": 1.60,
        "exit_reason": "target",
        "gap_minutes": 0,
    }])
    return raw, pd.read_csv(io.StringIO(raw.to_csv(index=False)))


@pytest.mark.parametrize("updates,error", [
    ({"cost": 0.50, "net_pnl": 1.50}, "fee differs"),
    ({"gross_pnl": 2.50, "net_pnl": 2.10}, "gross P/L differs"),
    ({"net_pnl": 1.90}, "net P/L differs"),
    ({"ounces": -1.0}, "nonpositive ounces"),
    ({"closed_at": pd.Timestamp("2024-01-01T00:00:00Z")}, "reversed"),
])
def test_matching_corruption_in_both_ledgers_is_rejected(updates, error):
    executed, _ = ledgers()
    for key, value in updates.items():
        executed.loc[0, key] = value
    exported = pd.read_csv(io.StringIO(executed.to_csv(index=False)))
    with pytest.raises(ValueError, match=error):
        verify_persisted_trade_ledger(executed, exported)


def test_matching_opposite_fee_errors_cannot_cancel_in_annual_total():
    executed, _ = ledgers()
    other = executed.copy()
    other["signal_at"] = pd.Timestamp("2024-01-02T00:00:00Z")
    other["entry_at"] = pd.Timestamp("2024-01-02T00:01:00Z")
    other["closed_at"] = pd.Timestamp("2024-01-02T00:03:00Z")
    executed = pd.concat([executed, other], ignore_index=True)
    executed.loc[0, ["cost", "net_pnl"]] = [0.50, 1.50]
    executed.loc[1, ["cost", "net_pnl"]] = [0.30, 1.70]
    assert executed["cost"].sum() == pytest.approx(0.80)
    assert executed["net_pnl"].sum() == pytest.approx(3.20)
    exported = pd.read_csv(io.StringIO(executed.to_csv(index=False)))
    with pytest.raises(ValueError, match="fee differs"):
        verify_persisted_trade_ledger(executed, exported)


def test_valid_two_ounce_trade_still_passes_fixed_per_ounce_cost():
    executed, _ = ledgers()
    executed.loc[0, ["ounces", "gross_pnl", "cost", "net_pnl"]] = [
        2.0, 4.0, 0.80, 3.20,
    ]
    exported = pd.read_csv(io.StringIO(executed.to_csv(index=False)))
    verify_persisted_trade_ledger(executed, exported)


@pytest.mark.parametrize("field,value", [
    ("entry_price", -100.0),
    ("exit_price", 0.0),
    ("stop", 0.0),
    ("target", -1.0),
])
def test_matching_nonpositive_price_is_rejected(field, value):
    executed, _ = ledgers()
    executed.loc[0, field] = value
    exported = pd.read_csv(io.StringIO(executed.to_csv(index=False)))
    with pytest.raises(ValueError, match="nonpositive price"):
        verify_persisted_trade_ledger(executed, exported)


@pytest.mark.parametrize("field,value", [
    ("stop", 100.0), ("stop", 101.0),
    ("target", 100.0), ("target", 99.0),
])
def test_matching_invalid_long_protective_geometry_is_rejected(field, value):
    executed, _ = ledgers()
    executed.loc[0, field] = value
    exported = pd.read_csv(io.StringIO(executed.to_csv(index=False)))
    with pytest.raises(ValueError, match="invalid stop/target geometry"):
        verify_persisted_trade_ledger(executed, exported)


def test_matching_invalid_short_protective_geometry_is_rejected():
    executed, _ = ledgers()
    executed.loc[0, ["side", "stop", "target", "gross_pnl", "net_pnl"]] = [
        -1, 99.0, 98.0, -2.0, -2.4,
    ]
    exported = pd.read_csv(io.StringIO(executed.to_csv(index=False)))
    with pytest.raises(ValueError, match="invalid stop/target geometry"):
        verify_persisted_trade_ledger(executed, exported)


def test_valid_short_trade_and_adverse_long_gap_stop_remain_supported():
    short, _ = ledgers()
    short.loc[0, ["side", "exit_price", "stop", "target"]] = [
        -1, 98.0, 101.0, 98.0,
    ]
    verify_persisted_trade_ledger(
        short, pd.read_csv(io.StringIO(short.to_csv(index=False)))
    )
    gap, _ = ledgers()
    gap.loc[0, ["exit_price", "gross_pnl", "net_pnl", "exit_reason"]] = [
        97.0, -3.0, -3.4, "gap_stop",
    ]
    verify_persisted_trade_ledger(
        gap, pd.read_csv(io.StringIO(gap.to_csv(index=False)))
    )
