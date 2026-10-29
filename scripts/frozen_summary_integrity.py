"""Independent fail-closed consistency gate for frozen annual summary claims.

This validates published summary metadata against executed trades and persisted
monthly buckets; it does not validate broker fills or out-of-sample status.
"""
from __future__ import annotations

import math

import pandas as pd


def _integer(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"Frozen summary {name} must be a nonnegative integer")
    return value


def _finite(value: object, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"Frozen summary {name} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Frozen summary {name} must be finite numeric")
    return result


def _equal_amount(value: object, expected: float, name: str) -> None:
    if not math.isclose(_finite(value, name), expected, rel_tol=0, abs_tol=1e-7):
        raise ValueError(f"Frozen summary {name} disagrees with independent ledger")


def verify_frozen_summary_claims(
    summary: dict, monthly: pd.DataFrame, trades: pd.DataFrame, *,
    year: int, source_sha: str, bidask_sha: str, m1_rows: int,
) -> None:
    """Reject misleading annual headline numbers or source/strategy provenance."""
    if type(summary) is not dict or not isinstance(monthly, pd.DataFrame) or not isinstance(trades, pd.DataFrame):
        raise ValueError("Frozen summary inputs must be structured ledgers")
    if type(year) is not int or type(m1_rows) is not int or m1_rows <= 0:
        raise ValueError("Frozen summary requires a valid annual M1 identity")
    if len(monthly) != 12 or "net_pnl" not in monthly or "net_pnl" not in trades or "cost" not in trades:
        raise ValueError("Frozen summary requires complete monthly and trade ledgers")
    monthly_net = pd.to_numeric(monthly["net_pnl"], errors="raise")
    trade_net = pd.to_numeric(trades["net_pnl"], errors="raise")
    trade_cost = pd.to_numeric(trades["cost"], errors="raise")
    if not (monthly_net.map(math.isfinite).all() and trade_net.map(math.isfinite).all()
            and trade_cost.map(math.isfinite).all()):
        raise ValueError("Frozen summary ledgers contain nonfinite values")
    if (trade_cost < 0).any():
        raise ValueError("Frozen summary trade costs cannot be negative")
    expected_counts = {
        "trades": len(trades),
        "wins": int((trade_net > 0).sum()),
        "positive_months": int((monthly_net > 0).sum()),
        "nonpositive_months": int((monthly_net <= 0).sum()),
        "months_observed": 12,
        "months_with_m1_observations": 12,
        "calendar_months_without_m1": 0,
    }
    for name, expected in expected_counts.items():
        if _integer(summary.get(name), name) != expected:
            raise ValueError(f"Frozen summary {name} disagrees with independent ledger")
    _equal_amount(summary.get("net_pnl"), float(trade_net.sum()), "net_pnl")
    _equal_amount(summary.get("total_fees"), float(trade_cost.sum()), "total_fees")
    _equal_amount(summary.get("total_fees"), .40 * len(trades), "fixed $0.40/oz fee")
    provenance = summary.get("source_fingerprints")
    if (type(provenance) is not dict
            or provenance.get("source_archive_sha256") != source_sha
            or provenance.get("loaded_m1_bidask_sha256") != bidask_sha
            or type(provenance.get("loaded_m1_rows")) is not int
            or provenance["loaded_m1_rows"] != m1_rows):
        raise ValueError("Frozen summary source provenance disagrees with loaded M1")
    params = summary.get("run_parameters")
    if (type(params) is not dict
            or params.get("year") != year or type(params.get("year")) is not int
            or params.get("strategy") != "bos_fib_m1_frozen_h1_120m_no_dual_pivots"
            or params.get("do_not_claim_clean_oos") is not True
            or type(params.get("cost_per_oz_all_in")) not in (int, float)
            or params["cost_per_oz_all_in"] != .40):
        raise ValueError("Frozen summary strategy or OOS disclaimer drifted")
