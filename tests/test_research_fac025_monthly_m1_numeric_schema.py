"""Strict FAC025 M1 monthly-risk evidence schema; synthetic data only."""
import pandas as pd
import pytest

from scripts.research_fac025_monthly_m1_risk import monthly_observed_m1_risk


def _marks():
    index = pd.to_datetime(["2026-01-01T00:00Z", "2026-01-01T00:01Z"], utc=True)
    source = pd.DataFrame({"o": [100., 101.]}, index=index)
    equity = pd.DataFrame({
        "equity": [0., -1.], "realized_pnl": [0., -1.],
        "floating_pnl": [0., 0.],
    }, index=index)
    return source, equity


@pytest.mark.parametrize("column,values", [
    ("equity", ["0", "-1"]),
    ("realized_pnl", [False, True]),
    ("floating_pnl", [0+0j, 0+0j]),
    ("equity", [0, "-1"]),
])
def test_implicit_numeric_coercion_is_not_evidence(column, values):
    source, equity = _marks()
    equity[column] = pd.Series(values, index=equity.index)
    with pytest.raises(ValueError, match="real numeric dtype"):
        monthly_observed_m1_risk(source, equity)


def test_duplicate_equity_column_names_rejected():
    source, equity = _marks()
    equity = pd.concat([equity, equity[["equity"]]], axis=1)
    with pytest.raises(ValueError, match="Duplicate M1 equity"):
        monthly_observed_m1_risk(source, equity)


def test_real_numeric_int_float_evidence_retains_monthly_risk():
    source, equity = _marks()
    equity["realized_pnl"] = equity["realized_pnl"].astype("int64")
    rows = monthly_observed_m1_risk(source, equity)
    assert rows[0]["observed_m1_equity_marks"] == 2
    assert rows[0]["month_local_max_observed_m1_close_drawdown_usd_per_oz"] == 1.
