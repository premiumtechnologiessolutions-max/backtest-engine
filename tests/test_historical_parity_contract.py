import pandas as pd
import pytest

from scripts.verify_bos_h1_parity import exact_ledger_check


def _case():
    at = pd.Timestamp("2024-01-02T00:01:00Z")
    enter = pd.Timestamp("2024-01-02T00:02:00Z")
    exit_at = pd.Timestamp("2024-01-02T00:04:00Z")
    actual = pd.DataFrame([{
        "signal_at": at, "entry_at": enter, "closed_at": exit_at,
        "side": 1, "entry_price": 100., "exit_price": 102.,
        "stop": 99., "target": 102., "gross_pnl": 2.,
        "cost": .4, "net_pnl": 1.6, "exit_reason": "target",
        "gap_minutes": 0,
    }])
    independent = pd.DataFrame([{
        "signal_time": int(at.timestamp()),
        "entry_time": int(enter.timestamp()),
        "exit_time": int(exit_at.timestamp()),
        "side": 1, "entry": 100., "exit": 102.,
        "stop": 99., "target": 102., "gross": 2.,
        "fee": .4, "net": 1.6, "exit_reason": "target",
        "gap_minutes": 0,
    }])
    return actual, independent


def test_independent_13_field_ledger_contract_passes_exact_match():
    current, archive = _case()
    record = exact_ledger_check(current, archive)
    assert record["fields"] == 13
    assert record["trades"] == 1
    assert record["max_abs_pnl_delta"] == 0


@pytest.mark.parametrize("field,value", [
    ("net_pnl", 2.0), ("cost", 0.8), ("entry_price", 100.01),
    ("exit_reason", "stop"), ("gap_minutes", 9),
    ("entry_at", pd.Timestamp("2024-01-02T00:03:00Z")),
])
def test_replay_contract_fails_if_any_material_execution_field_changes(field, value):
    current, archive = _case()
    current.loc[0, field] = value
    with pytest.raises(AssertionError, match="First differing field"):
        exact_ledger_check(current, archive)


def test_reference_trade_count_drift_is_not_hidden():
    current, archive = _case()
    with pytest.raises(AssertionError, match="Trade count mismatch"):
        exact_ledger_check(current.iloc[0:0], archive)
