"""FAC025 frozen-spec -> canonical BID/ASK receipt gate bridge.

This binds ONLY the already frozen 72 correlated filter settings to the
existing receipt-checked research gate. It does not define entries, exits,
position sizing, shared-capacity execution, backtests or live orders.
"""
from __future__ import annotations

from datetime import datetime

try:
    from scripts.research_fac025_frozen_grid import validate_frozen_spec
    from scripts.research_fac025_canonical_receipts import (
        evaluate_fac025_with_canonical_receipts,
    )
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from research_fac025_frozen_grid import validate_frozen_spec
    from research_fac025_canonical_receipts import (
        evaluate_fac025_with_canonical_receipts,
    )


def evaluate_frozen_fac025_receipts(
    signal_at: datetime,
    paired_m1: list[dict],
    canonical_trades: list[dict],
    *,
    spec_id: str,
    parameters: dict,
    fingerprint: str,
) -> dict:
    """Validate the exact frozen ID/parameter fingerprint before any gate call.

    No arbitrary parameter override is accepted. The pre-existing adapters
    independently check paired BID/ASK completion receipts, trade confirmation
    times, fee reconciliation, strict M15 chronology, NY DST and daily loss.
    Passing means FILTER-ELIGIBLE only, never an executable strategy.
    """
    if type(spec_id) is not str:
        raise ValueError("FAC025 spec_id must be a frozen string ID")
    spec = validate_frozen_spec(parameters, fingerprint)
    if spec_id != spec["id"]:
        raise ValueError("FAC025 spec ID/fingerprint mismatch")
    p = spec["parameters"]
    result = evaluate_fac025_with_canonical_receipts(
        signal_at,
        paired_m1,
        canonical_trades,
        lookback=p["lookback"],
        min_range_ratio=float(p["min_range_ratio"]),
        max_range_ratio=float(p["max_range_ratio"]),
        daily_loss_halt=float(p["daily_loss_halt"]),
        session_start_hour=p["session_start_hour"],
        session_end_hour=p["session_end_hour"],
    )
    result["frozen_spec"] = {
        "id": spec["id"],
        "fingerprint": spec["fingerprint"],
        "hypothesis": "NRF-FAC-025",
        "correlated_parameter_spec": True,
        "entry_exit_defined": False,
        "shared_capacity_backtest_verified": False,
        "monthly_net_pnl_usd_per_oz": "N/A",
        "floating_m1_drawdown_usd_per_oz": "N/A",
    }
    return result
