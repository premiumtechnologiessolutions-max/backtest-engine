"""Fail-closed archived CSV ingress for independent 13-field replay.

Synthetic CSV only. No private XAUUSD data or OOS samples.
"""
import pandas as pd
import pytest

from scripts.verify_bos_h1_parity import FIELDS, read_reference_csv


@pytest.mark.parametrize("data", [
    "a,b\n1,2\n",
    "\ufeffa,b\n1,2\n",
])
def test_reference_csv_accepts_regular_and_utf8_bom_headers(tmp_path, data):
    path = tmp_path / "valid.csv"
    path.write_text(data, encoding="utf-8")
    actual = read_reference_csv(path, required_columns={"a", "b"})
    assert actual.to_dict("records") == [{"a": 1, "b": 2}]


@pytest.mark.parametrize("data,reason", [
    ("a,a\n1,2\n", "duplicate header"),
    ("a,b\n1\n", "fields"),
    ("a,b\n1,2,3\n", "fields"),
    ("a,b\n\"unclosed,2\n", "malformed"),
    ("", "header"),
    ("a,\n1,2\n", "header"),
    ("a,c\n1,2\n", "missing required"),
])
def test_reference_csv_rejects_ambiguous_or_truncated_records(tmp_path, data, reason):
    path = tmp_path / "corrupt.csv"
    path.write_text(data, encoding="utf-8")
    with pytest.raises(ValueError, match=reason):
        read_reference_csv(path, required_columns={"a", "b"})


def test_reference_csv_rejects_symlink_even_to_valid_file(tmp_path):
    real = tmp_path / "real.csv"
    real.write_text("a,b\n1,2\n", encoding="utf-8")
    link = tmp_path / "alias.csv"
    link.symlink_to(real)
    with pytest.raises(ValueError, match="symlink"):
        read_reference_csv(link, required_columns={"a", "b"})
    assert real.read_text(encoding="utf-8") == "a,b\n1,2\n"


def test_reference_csv_requires_all_thirteen_archived_execution_columns(tmp_path):
    path = tmp_path / "trades.csv"
    columns = list(FIELDS.values())
    path.write_text(",".join(columns) + "\n", encoding="utf-8")
    actual = read_reference_csv(path, required_columns=set(columns))
    assert isinstance(actual, pd.DataFrame)
    assert actual.empty
    assert set(columns).issubset(actual.columns)
    path.write_text(",".join(columns[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required"):
        read_reference_csv(path, required_columns=set(columns))
