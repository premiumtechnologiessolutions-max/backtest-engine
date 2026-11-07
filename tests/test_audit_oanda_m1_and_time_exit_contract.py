"""Regression checks for offline OANDA contract and audited time exits."""
from datetime import datetime, timezone
import pandas as pd
import pytest

from norisk_quant.oanda_readonly import parse_closed_m1
from norisk_quant.persisted_trade_integrity import verify_persisted_trade_ledger


def test_declared_h1_must_not_be_interpreted_as_m1():
    payload = {"instrument": "XAU_USD", "granularity": "H1", "candles": []}
    with pytest.raises(ValueError, match="granularity"):
        parse_closed_m1(payload, "XAU_USD")


def test_declared_mid_only_quotes_must_not_pass_bid_ask_contract():
    payload = {"instrument": "XAU_USD", "price": "M", "candles": []}
    with pytest.raises(ValueError, match="BID/ASK"):
        parse_closed_m1(payload, "XAU_USD")


def test_persisted_ledger_permits_valid_time_exit_with_15_field_parity():
    t0 = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 11, 1, 0, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 1, 0, 6, tzinfo=timezone.utc)
    row = {"strategy": "ema", "signal_at": t0, "entry_at": t1, "closed_at": t2,
           "side": 1, "entry_price": 2000.0, "exit_price": 2001.0,
           "stop": 1990.0, "target": 2010.0, "ounces": 1.0,
           "gross_pnl": 1.0, "cost": .4, "net_pnl": .6,
           "exit_reason": "time_exit", "gap_minutes": 0}
    executed = pd.DataFrame([row])
    exported = executed.copy()
    for field in ("signal_at", "entry_at", "closed_at"):
        exported[field] = [row[field].isoformat()]
    verify_persisted_trade_ledger(executed, exported)


def test_unknown_exit_reason_is_still_rejected():
    t0 = datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc)
    row = {"strategy": "ema", "signal_at": t0, "entry_at": t0,
           "closed_at": t0, "side": 1, "entry_price": 2000.0,
           "exit_price": 2001.0, "stop": 1990.0, "target": 2010.0,
           "ounces": 1.0, "gross_pnl": 1.0, "cost": .4, "net_pnl": .6,
           "exit_reason": "unrecognised", "gap_minutes": 0}
    executed = pd.DataFrame([row])
    exported = executed.copy()
    for field in ("signal_at", "entry_at", "closed_at"):
        exported[field] = [t0.isoformat()]
    with pytest.raises(ValueError, match="unknown exit reason"):
        verify_persisted_trade_ledger(executed, exported)
