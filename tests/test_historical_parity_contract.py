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



@pytest.mark.parametrize("field,value", [
    ("entry_at", pd.Timestamp("2024-01-02T00:02:00.500Z")),
    ("side", 1.000000001),
    ("gap_minutes", 0.000000001),
])
def test_replay_contract_rejects_subsecond_or_discrete_field_drift(field, value):
    current, archive = _case()
    if field in {"side", "gap_minutes"}:
        # Preserve compatibility with future pandas versions that reject
        # assigning a fractional float into an int64 column.
        current[field] = current[field].astype(float)
    current.loc[0, field] = value
    with pytest.raises(AssertionError, match=f"First differing field: {field}"):
        exact_ledger_check(current, archive)


def test_zero_trade_replay_still_requires_all_thirteen_columns():
    current, archive = _case()
    assert exact_ledger_check(current.iloc[:0], archive.iloc[:0])["trades"] == 0
    current = current.iloc[:0].drop(columns=["entry_at"])
    with pytest.raises(AssertionError, match="Missing ledger field entry_at/entry_time"):
        exact_ledger_check(current, archive.iloc[:0])


@pytest.mark.parametrize("field,bad", [
    ("side", True), ("side", 1.0), ("side", 2),
    ("gap_minutes", False), ("gap_minutes", 0.0), ("gap_minutes", -1),
])
@pytest.mark.parametrize("ledger", ["actual", "reference"])
def test_replay_rejects_noninteger_or_invalid_discrete_fields_on_either_side(
    field, bad, ledger
):
    """NumPy array_equal regards True == 1 and 0.0 == 0 as equal."""
    current, archive = _case()
    if ledger == "actual":
        # Object dtype preserves bool vs int for a strict schema check.
        current[field] = pd.Series([bad], dtype=object)
    else:
        archive[field] = pd.Series([bad], dtype=object)
    with pytest.raises(AssertionError, match=f"First differing field: {field}"):
        exact_ledger_check(current, archive)


def test_replay_still_accepts_native_integer_discrete_fields():
    current, archive = _case()
    assert exact_ledger_check(current, archive)["fields"] == 13


@pytest.mark.parametrize("field,archived_field", [
    ("gross_pnl", "gross"),
    ("net_pnl", "net"),
    ("entry_price", "entry"),
    ("cost", "fee"),
])
def test_replay_rejects_matching_infinities_in_numeric_fields(field, archived_field):
    # np.allclose(inf, inf) otherwise reports a match.
    current, archive = _case()
    current[field] = float("inf")
    archive[archived_field] = float("inf")
    with pytest.raises(AssertionError, match=f"First differing field: {field}"):
        exact_ledger_check(current, archive)


@pytest.mark.parametrize("field,archived_field", [
    ("signal_at", "signal_time"),
    ("entry_at", "entry_time"),
    ("closed_at", "exit_time"),
])
def test_replay_rejects_fractional_archived_unix_seconds(field, archived_field):
    # A dtype=int64 cast truncates these to the correct whole second.
    current, archive = _case()
    archive[archived_field] = archive[archived_field].astype(float) + 0.5
    with pytest.raises(AssertionError, match=f"First differing field: {field}"):
        exact_ledger_check(current, archive)


def test_replay_rejects_naive_engine_timestamp_even_when_utc_wall_clock_matches():
    # utc=True alone would silently localize this naive timestamp to UTC.
    current, archive = _case()
    current["entry_at"] = current["entry_at"].dt.tz_localize(None)
    with pytest.raises(AssertionError, match="First differing field: entry_at"):
        exact_ledger_check(current, archive)


def test_replay_rejects_invalid_reference_timestamp_type():
    current, archive = _case()
    archive["signal_time"] = archive["signal_time"].astype(str)
    with pytest.raises(AssertionError, match="First differing field: signal_at"):
        exact_ledger_check(current, archive)


@pytest.mark.parametrize("field,archive_field", [
    ("entry_price", "entry"), ("net_pnl", "net"), ("cost", "fee"),
])
@pytest.mark.parametrize("invalid", [True, "100.0"])
@pytest.mark.parametrize("ledger", ["actual", "reference"])
def test_replay_rejects_numeric_bool_or_string_coercion(
    field, archive_field, invalid, ledger
):
    """Even values that float() can parse are not valid numeric ledger cells."""
    current, archive = _case()
    if ledger == "actual":
        current[field] = pd.Series([invalid], dtype=object)
    else:
        archive[archive_field] = pd.Series([invalid], dtype=object)
    with pytest.raises(AssertionError, match=f"First differing field: {field}"):
        exact_ledger_check(current, archive)


@pytest.mark.parametrize("ledger", ["actual", "reference"])
@pytest.mark.parametrize("bad", [1, "", None])
def test_replay_rejects_nontext_or_empty_exit_reasons(ledger, bad):
    current, archive = _case()
    target = current if ledger == "actual" else archive
    target["exit_reason"] = pd.Series([bad], dtype=object)
    with pytest.raises(AssertionError, match="First differing field: exit_reason"):
        exact_ledger_check(current, archive)


def test_replay_still_accepts_numeric_and_text_fields_without_coercion():
    current, archive = _case()
    assert exact_ledger_check(current, archive)["trades"] == 1
