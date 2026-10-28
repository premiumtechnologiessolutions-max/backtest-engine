"""Synthetic tests only: no raw XAUUSD data or broker-fill claims."""
import io

import pandas as pd
import pytest

from norisk_quant.persisted_trade_integrity import (
    FIELDS, verify_persisted_trade_ledger,
)


def ledgers():
    row = dict(
        strategy="bos",
        signal_at=pd.Timestamp("2024-01-01T00:00Z"),
        entry_at=pd.Timestamp("2024-01-01T00:01Z"),
        closed_at=pd.Timestamp("2024-01-01T00:03Z"),
        side=1, entry_price=100.0, exit_price=102.0,
        stop=99.0, target=102.0, ounces=1.0,
        gross_pnl=2.0, cost=.4, net_pnl=1.6,
        exit_reason="target", gap_minutes=0,
    )
    raw = pd.DataFrame([row])
    saved = pd.read_csv(io.StringIO(raw.to_csv(index=False)))
    return raw, saved


def test_roundtrip():
    a, b = ledgers()
    verify_persisted_trade_ledger(a, b)


def test_empty_schema():
    a, b = ledgers()
    verify_persisted_trade_ledger(a.iloc[:0], b.iloc[:0])


@pytest.mark.parametrize("field,value", [
    ("entry_price", 100.2), ("exit_price", 102.2), ("net_pnl", 1.7),
    ("signal_at", "2024-01-01 00:00:01+00:00"),
    ("entry_at", "2024-01-01 00:01:01+00:00"),
    ("closed_at", "2024-01-01 00:04:00+00:00"),
    ("side", -1), ("gap_minutes", 1), ("strategy", "other"),
    ("exit_reason", "stop"), ("cost", 0.5), ("ounces", 2.0),
])
def test_mismatch(field, value):
    a, b = ledgers()
    b.loc[0, field] = value
    with pytest.raises(ValueError, match="differs from execution"):
        verify_persisted_trade_ledger(a, b)


@pytest.mark.parametrize("field", FIELDS)
def test_missing_column(field):
    a, b = ledgers()
    b = b.drop(columns=[field])
    with pytest.raises(ValueError, match="missing/duplicate"):
        verify_persisted_trade_ledger(a, b)


def test_naive_export_timestamp():
    a, b = ledgers()
    b["closed_at"] = "2024-01-01 00:03:00"
    with pytest.raises(ValueError, match="invalid UTC"):
        verify_persisted_trade_ledger(a, b)


def test_matching_nonfinite_is_rejected():
    a, b = ledgers()
    a["net_pnl"] = float("inf")
    b["net_pnl"] = float("inf")
    with pytest.raises(ValueError, match="Nonfinite"):
        verify_persisted_trade_ledger(a, b)


def test_zero_rows_still_require_schema():
    a, b = ledgers()
    b = b.drop(columns=["net_pnl"])
    with pytest.raises(ValueError, match="missing/duplicate"):
        verify_persisted_trade_ledger(a.iloc[:0], b.iloc[:0])


def test_reordered_rows_rejected():
    a, b = ledgers()
    a2 = a.copy()
    a2["entry_price"] = 101.0
    aa = pd.concat([a, a2], ignore_index=True)
    bb = pd.read_csv(io.StringIO(aa.to_csv(index=False))).iloc[::-1].reset_index(drop=True)
    with pytest.raises(ValueError, match="differs from execution"):
        verify_persisted_trade_ledger(aa, bb)


def test_empty_execution_missing_fields_is_rejected():
    """An incomplete engine ledger must fail before monthly P/L allocation."""
    executed, exported = ledgers()
    executed = executed[["net_pnl"]].iloc[:0]
    exported = exported.iloc[:0]
    with pytest.raises(ValueError, match="execution trade ledger has missing/duplicate"):
        verify_persisted_trade_ledger(executed, exported)
