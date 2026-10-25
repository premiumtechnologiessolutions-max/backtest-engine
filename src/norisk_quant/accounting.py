"""Strict execution/accounting invariants for research-grade M1 backtests."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .execution import Result
from .model import Settings


def validate_execution(result: Result, settings: Settings, *, atol: float = 1e-7) -> dict:
    """Fail closed on fee, P/L, timestamp, equity and mark-to-market drift.

    Does NOT assert that synthetic OHLC prices were executable broker fills.
    """
    if atol <= 0:
        raise ValueError("atol must be positive")
    trades = result.trades
    equity = result.equity
    if equity.empty or not {"realized_pnl", "floating_pnl", "equity"}.issubset(equity.columns):
        raise ValueError("Missing equity samples")
    if equity.index.has_duplicates or not equity.index.is_monotonic_increasing:
        raise ValueError("Unordered equity observations")
    numeric_eq = equity[["realized_pnl", "floating_pnl", "equity"]].to_numpy(dtype=float)
    if not np.isfinite(numeric_eq).all():
        raise ValueError("NaN/Infinity in equity")
    if not np.allclose(
        numeric_eq[:, 0] + numeric_eq[:, 1], numeric_eq[:, 2],
        rtol=0, atol=atol
    ):
        raise ValueError("Equity ledger fails realized + floating reconciliation")

    fixed_fee = settings.ounces * settings.roundtrip_cost_per_ounce
    allowed_reasons = {
        "gap_stop", "open_stop", "open_target", "stop",
        "target", "ambiguous_stop_first", "end_of_data",
        "entry_open_beyond_stop",
    }
    synthetic_count = 0
    if not trades.empty:
        required = {
            "entry_at", "closed_at", "signal_at", "side", "entry_price",
            "exit_price", "ounces", "gross_pnl", "cost", "net_pnl", "exit_reason",
        }
        if not required.issubset(trades):
            raise ValueError(f"Trade ledger missing {sorted(required - set(trades.columns))}")
        entry = pd.to_datetime(trades["entry_at"], utc=True)
        exit_time = pd.to_datetime(trades["closed_at"], utc=True)
        signal_time = pd.to_datetime(trades["signal_at"], utc=True)
        if (
            entry.isna().any() or exit_time.isna().any() or signal_time.isna().any()
            or (entry < signal_time).any() or (exit_time < entry).any()
            or (entry < equity.index[0]).any() or (exit_time > equity.index[-1]).any()
        ):
            raise ValueError("Causality or execution-window violation")
        if not trades["exit_reason"].isin(allowed_reasons).all():
            raise ValueError("Unknown trade exit reason")
        if not trades["side"].isin((1, -1)).all():
            raise ValueError("Illegal trade side")
        values = trades[[
            "entry_price", "exit_price", "ounces", "gross_pnl", "cost", "net_pnl",
        ]].to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("NaN/Infinity in trade ledger")
        entry_price, exit_price, ounces, gross, costs, net = values.T
        if (entry_price <= 0).any() or (exit_price <= 0).any():
            raise ValueError("Non-positive reference price")
        if not np.allclose(ounces, settings.ounces, rtol=0, atol=atol):
            raise ValueError("Unexpected trade quantity")
        if not np.allclose(costs, fixed_fee, rtol=0, atol=atol):
            raise ValueError("Fee drift or double-counted spread/commission")
        expected_gross = trades["side"].to_numpy() * (
            exit_price - entry_price
        ) * settings.ounces
        if not np.allclose(gross, expected_gross, rtol=0, atol=atol):
            raise ValueError("Gross P/L mismatch")
        if not np.allclose(net, gross - costs, rtol=0, atol=atol):
            raise ValueError("Net P/L mismatch")
        # Simulator promises at most one position at a time.
        ordered = trades.assign(_entry=entry, _exit=exit_time).sort_values("_entry")
        if (ordered["_entry"].iloc[1:].to_numpy() <
                ordered["_exit"].iloc[:-1].to_numpy()).any():
            raise ValueError("Overlapping trades in single-position execution")
        synthetic_count = int((trades["exit_reason"] == "end_of_data").sum())

    total = float(trades["net_pnl"].sum()) if not trades.empty else 0.0
    last = float(equity["equity"].iloc[-1])
    if result.pending_at_end < 0 or result.expired_signals < 0:
        raise ValueError("Negative signal counts")
    if not math.isclose(total, last, rel_tol=0, abs_tol=atol):
        # If close_at_end=False, open P&L can remain in equity.
        if settings.close_at_end:
            raise ValueError("Closed-trade P/L and last equity disagree")
    return {
        "accounting_checks": "PASSED",
        "trades": int(len(trades)),
        "total_cost": float(trades["cost"].sum()) if not trades.empty else 0.0,
        "net_pnl": total,
        "forced_end_of_data_closures": synthetic_count,
        "forced_end_of_data_pnl": float(
            trades.loc[trades["exit_reason"] == "end_of_data", "net_pnl"].sum()
        ) if not trades.empty else 0.0,
        "note": "Accounting validation does not verify missing tick paths or broker fills.",
    }
