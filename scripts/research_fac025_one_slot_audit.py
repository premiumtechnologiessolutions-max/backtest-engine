"""Conservative one-slot CLOSED-ledger audit for FAC025 research.

This does NOT replay signals, check open positions, or certify executable
shared capacity. It only rejects overlaps in already canonical-reconciled
closed fills. Same-timestamp exit/re-entry is rejected because M1 OHLC cannot
establish intraminute order without independent evidence.
"""
from __future__ import annotations

from datetime import datetime

try:
    from scripts.research_fac025_canonical_receipts import reconcile_canonical_closed_receipts
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from research_fac025_canonical_receipts import reconcile_canonical_closed_receipts


def audit_one_slot_closed_history(trades: list[dict], decision_at: datetime) -> dict:
    """Fail closed on overlap, using existing canonical fees/receipt validation.

    A passing result is NOT an executable portfolio backtest: it cannot prove
    that skipped competing signals, currently open positions, or intraminute
    execution were handled correctly.
    """
    reconciled = reconcile_canonical_closed_receipts(trades, decision_at)
    prior_closed = None
    for row in trades:
        entry = row["entry_at"]
        if prior_closed is not None and entry <= prior_closed:
            raise ValueError(
                "One-slot closed ledger overlaps or has unproven same-instant "
                "exit/re-entry ordering"
            )
        prior_closed = row["closed_at"]
    return {
        "closed_trades_reconciled": len(reconciled),
        "closed_history_overlap_count": 0,
        "audit_scope": "CLOSED_LEDGER_NONOVERLAP_ONLY",
        "shared_capacity_backtest_verified": False,
        "open_position_at_decision": "UNKNOWN",
        "monthly_net_pnl_usd_per_oz": "N/A",
        "floating_m1_drawdown_usd_per_oz": "N/A",
    }
