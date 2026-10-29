"""Purely synthetic annual summary regression tests; no market source data."""
import pandas as pd
import pytest
from scripts.frozen_summary_integrity import verify_frozen_summary_claims

SHA = "a" * 64
BIDASK = "b" * 64


def _fixture():
    monthly = pd.DataFrame({"net_pnl": [1.0, -2.0] + [0.0] * 10})
    trades = pd.DataFrame({"net_pnl": [1.0, -2.0], "cost": [.40, .40]})
    summary = {
        "trades": 2, "wins": 1, "positive_months": 1,
        "nonpositive_months": 11, "months_observed": 12,
        "months_with_m1_observations": 12,
        "calendar_months_without_m1": 0,
        "net_pnl": -1.0, "total_fees": .80,
        "source_fingerprints": {
            "source_archive_sha256": SHA,
            "loaded_m1_bidask_sha256": BIDASK,
            "loaded_m1_rows": 120,
        },
        "run_parameters": {
            "year": 2012, "strategy": "bos_fib_m1_frozen_h1_120m_no_dual_pivots",
            "do_not_claim_clean_oos": True, "cost_per_oz_all_in": .40,
        },
    }
    return summary, monthly, trades


def _check(summary, monthly, trades):
    verify_frozen_summary_claims(summary, monthly, trades, year=2012,
                                 source_sha=SHA, bidask_sha=BIDASK, m1_rows=120)


def test_consistent_frozen_summary_accepted():
    _check(*_fixture())


@pytest.mark.parametrize("field,wrong", [
    ("trades", 3), ("wins", 2), ("positive_months", 12),
    ("nonpositive_months", 10), ("months_observed", 11),
    ("months_with_m1_observations", 11),
    ("calendar_months_without_m1", 1), ("net_pnl", 0),
    ("total_fees", .4), ("trades", True), ("wins", float("nan")),
])
def test_false_headline_is_rejected(field, wrong):
    summary, monthly, trades = _fixture()
    summary[field] = wrong
    with pytest.raises(ValueError, match="Frozen summary"):
        _check(summary, monthly, trades)


@pytest.mark.parametrize("field,wrong", [
    ("source_archive_sha256", "c" * 64),
    ("loaded_m1_bidask_sha256", "c" * 64),
    ("loaded_m1_rows", 119),
    ("loaded_m1_rows", True),
])
def test_false_source_provenance_is_rejected(field, wrong):
    summary, monthly, trades = _fixture()
    summary["source_fingerprints"][field] = wrong
    with pytest.raises(ValueError, match="provenance"):
        _check(summary, monthly, trades)


@pytest.mark.parametrize("field,wrong", [
    ("year", 2013), ("year", True), ("strategy", "unfrozen"),
    ("do_not_claim_clean_oos", False), ("cost_per_oz_all_in", 0),
])
def test_strategy_or_disclaimer_drift_is_rejected(field, wrong):
    summary, monthly, trades = _fixture()
    summary["run_parameters"][field] = wrong
    with pytest.raises(ValueError, match="strategy or OOS"):
        _check(summary, monthly, trades)


def test_nonfinite_monthly_and_negative_cost_rejected():
    summary, monthly, trades = _fixture()
    monthly.loc[0, "net_pnl"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        _check(summary, monthly, trades)
    summary, monthly, trades = _fixture()
    trades.loc[0, "cost"] = -.4
    with pytest.raises(ValueError, match="negative"):
        _check(summary, monthly, trades)


def test_monthly_net_must_reconcile_to_trade_ledger():
    summary, monthly, trades = _fixture()
    monthly.loc[0, "net_pnl"] = 2.0  # positive-month count unchanged
    with pytest.raises(ValueError, match="monthly net"):
        _check(summary, monthly, trades)


def test_offsetting_fee_tampering_is_rejected():
    summary, monthly, trades = _fixture()
    trades["cost"] = [.20, .60]  # annual fee total still exactly $0.80
    with pytest.raises(ValueError, match="per-trade fee"):
        _check(summary, monthly, trades)


@pytest.mark.parametrize("ledger,column,values", [
    ("monthly", "net_pnl", ["1.0", "-2.0"] + ["0.0"] * 10),
    ("trades", "net_pnl", ["1.0", "-2.0"]),
    ("trades", "cost", ["0.4", "0.4"]),
    ("trades", "cost", [True, False]),
    ("trades", "net_pnl", [1 + 0j, -2 + 0j]),
])
def test_coercible_but_unverified_ledger_types_rejected(ledger, column, values):
    summary, monthly, trades = _fixture()
    target = monthly if ledger == "monthly" else trades
    target[column] = values
    with pytest.raises(ValueError, match="real numeric"):
        _check(summary, monthly, trades)


@pytest.mark.parametrize("ledger", ["monthly", "trades"])
def test_duplicate_ledger_column_labels_rejected(ledger):
    summary, monthly, trades = _fixture()
    target = monthly if ledger == "monthly" else trades
    target["duplicate"] = target["net_pnl"]
    target.rename(columns={"duplicate": "net_pnl"}, inplace=True)
    with pytest.raises(ValueError, match="duplicate column"):
        _check(summary, monthly, trades)


def test_empty_trade_ledger_remains_valid():
    summary, monthly, trades = _fixture()
    monthly["net_pnl"] = [0.0] * 12
    trades = pd.DataFrame(columns=["net_pnl", "cost"])
    summary.update(trades=0, wins=0, positive_months=0, nonpositive_months=12,
                   net_pnl=0.0, total_fees=0.0)
    _check(summary, monthly, trades)
