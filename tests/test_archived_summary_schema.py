"""Strict yearly-summary schema for the private 13-field historical replay.

Only synthetic reference-summary rows; no original gold prices are stored.
"""
import numpy as np
import pandas as pd
import pytest

from scripts.verify_bos_h1_parity import validate_reference_summary_row


def _row():
    return pd.Series({
        "year": 2012, "variant": "h1_only", "trades": np.int64(689),
        "orders": np.int64(800), "net_usd_oz": np.float64(-20.5),
    }, dtype=object)


def test_valid_native_summary_row_is_accepted():
    assert validate_reference_summary_row(_row()) == (689, 800, -20.5)


def test_zero_trade_summary_is_not_artificially_rejected():
    row = _row()
    row["trades"] = 0
    row["orders"] = 0
    row["net_usd_oz"] = 0
    assert validate_reference_summary_row(row) == (0, 0, 0.0)


@pytest.mark.parametrize("field,bad", [
    ("trades", 689.9), ("trades", 689.0), ("trades", True),
    ("trades", "689"), ("trades", -1), ("trades", np.nan),
    ("orders", 800.5), ("orders", False), ("orders", "800"),
    ("orders", -1), ("orders", np.inf),
    ("net_usd_oz", np.nan), ("net_usd_oz", np.inf),
    ("net_usd_oz", -np.inf), ("net_usd_oz", True),
    ("net_usd_oz", "-20.5"),
])
def test_corrupt_yearly_summary_cannot_be_coerced_to_pass(field, bad):
    row = _row()
    row[field] = bad
    with pytest.raises(AssertionError, match="Archived yearly summary"):
        validate_reference_summary_row(row)


def test_archived_trades_cannot_exceed_archived_orders():
    row = _row()
    row["trades"] = 801
    with pytest.raises(AssertionError, match="trades exceed orders"):
        validate_reference_summary_row(row)


def test_realistic_csv_pandas_row_dtypes_are_accepted(tmp_path):
    path = tmp_path / "yearly.csv"
    path.write_text(
        "year,variant,trades,orders,net_usd_oz\n"
        "2012,h1_only,689,800,-20.5\n", encoding="utf-8"
    )
    row = pd.read_csv(path).iloc[0]
    assert validate_reference_summary_row(row) == (689, 800, -20.5)
