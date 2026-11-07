"""FAC025 frozen intent -> one-slot canonical BID-only research replay.

Not source-authenticated BID/ASK execution, independent OOS, or live trading.
"""
from __future__ import annotations
from datetime import datetime, timedelta
import math
import numpy as np
import pandas as pd
from norisk_quant.execution import run
from norisk_quant.fast_engine import run_fast
from norisk_quant.model import Settings, Signal
from scripts.research_fac025_frozen_entry_policy import POLICY_SHA256, frozen_policy_fingerprint
from scripts.research_fac025_frozen_grid import frozen_specs
from scripts.research_fac025_monthly_m1_risk import monthly_observed_m1_risk

FEE = 0.40
STRATEGY = "FAC025_ENTRY_A_ONE_CORRELATED_HYPOTHESIS"


def _stamp(value, name):
    if type(value) is not str:
        raise ValueError(f"{name} must be an ISO UTC string")
    try:
        stamp = pd.Timestamp(datetime.fromisoformat(value))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"Invalid {name}") from exc
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be explicitly UTC")
    return stamp.tz_convert("UTC")


def _distance(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"Invalid {name}")
    return float(value)


def frozen_signals(intents):
    """Fail closed on changed frozen intent; no source provenance claim."""
    if type(intents) is not list or len(intents) > 100_000:
        raise ValueError("Intents must be a bounded list")
    frozen_policy_fingerprint()
    specs = {s["id"]: s["fingerprint"] for s in frozen_specs()}
    seen, entries = set(), []
    for intent in intents:
        if type(intent) is not dict or any((
            intent.get("status") != "RESEARCH_INTENT_ONLY",
            intent.get("frozen_entry_policy") != "FAC025-ENTRY-A",
            intent.get("policy_sha256") != POLICY_SHA256,
            intent.get("execution") != "RESEARCH_INTENT_ONLY_NO_FILLS_NO_ORDERS",
            type(intent.get("max_entry_delay_seconds")) is not int,
            intent.get("max_entry_delay_seconds") != 60,
            type(intent.get("shared_capacity_slots")) is not int,
            intent.get("shared_capacity_slots") != 1,
            intent.get("risk_sizing") != "UNDEFINED_NO_POSITION_SIZE",
            any(intent.get(k) != "N/A" for k in ("entry_price", "stop_price", "target_price")),
        )):
            raise ValueError("FAC025 frozen research intent was altered")
        spec_id = intent.get("filter_spec_id")
        if type(spec_id) is not str or specs.get(spec_id) != intent.get("filter_fingerprint"):
            raise ValueError("Unknown FAC025 frozen filter fingerprint")
        side = intent.get("side")
        if type(side) is not str or side not in ("BUY", "SELL"):
            raise ValueError("Invalid frozen side")
        if (type(intent.get("fee_usd_per_oz_all_in_roundtrip")) not in (int, float)
                or intent["fee_usd_per_oz_all_in_roundtrip"] != FEE):
            raise ValueError("Frozen $0.40/oz fee was altered")
        at = _stamp(intent.get("signal_at"), "signal_at")
        deadline = _stamp(intent.get("entry_deadline_utc"), "entry_deadline_utc")
        if deadline - at != pd.Timedelta(minutes=1):
            raise ValueError("Frozen 60s deadline was altered")
        stop = _distance(intent.get("risk_distance_usd_per_oz"), "stop distance")
        target = _distance(intent.get("target_distance_usd_per_oz"), "target distance")
        if not math.isclose(target, 1.5 * stop, rel_tol=0, abs_tol=1.6e-8):
            raise ValueError("Frozen 1.50 reward multiple was altered")
        key = (at.value, spec_id, side)
        if key in seen:
            raise ValueError("Duplicate frozen intent")
        seen.add(key)
        # Canonical engine permits entry at confirmation instant. FAC025
        # requires STRICTLY AFTER; 1ns barrier prevents same-open execution.
        signal = Signal(at + pd.Timedelta(nanoseconds=1),
                        1 if side == "BUY" else -1, stop, target, STRATEGY)
        entries.append((at.value, spec_id, side, signal))
    return [item[3] for item in sorted(entries, key=lambda item: item[:3])]


def _observed_utc_months(minutes):
    """Fail closed rather than booking fabricated zero-P/L unobserved months.

    Nonempty observed months are necessary, NOT proof of complete market
    sessions or clean OOS coverage. Never interpolate missing M1 bars.
    """
    if not isinstance(minutes, pd.DataFrame) or minutes.empty:
        raise ValueError("FAC025 requires nonempty observed M1")
    index = minutes.index
    if (not isinstance(index, pd.DatetimeIndex) or index.tz is None
            or index.hasnans or not index.is_monotonic_increasing
            or not index.is_unique):
        raise ValueError("FAC025 requires sorted unique timezone-aware M1 index")
    utc = index.tz_convert("UTC")
    if np.any(utc.as_unit("ns").asi8 % 60_000_000_000):
        raise ValueError("FAC025 M1 timestamps must be minute-aligned")
    counts = utc.tz_localize(None).to_period("M").value_counts().sort_index()
    expected = pd.period_range(counts.index[0], counts.index[-1], freq="M")
    missing = expected.difference(counts.index)
    if len(missing):
        raise ValueError("FAC025 missing observed UTC calendar month(s): "
                         + ", ".join(map(str, missing)))
    return counts


def replay_frozen_intents_bid_reference(minutes, intents):
    """Execute one canonical BID-proxy position and audit all M1 parity marks."""
    signals = frozen_signals(intents)
    observed_months = _observed_utc_months(minutes)
    settings = Settings(ounces=1.0, roundtrip_cost_per_ounce=FEE,
                        max_entry_delay_minutes=1, close_at_end=True)
    reference = run(minutes, signals, settings)
    fast = run_fast(minutes, signals, settings)
    pd.testing.assert_frame_equal(reference.trades, fast.trades,
                                  check_dtype=False, check_exact=False, atol=1e-8, rtol=0)
    pd.testing.assert_frame_equal(reference.equity, fast.equity,
                                  check_dtype=False, check_exact=False, atol=1e-8, rtol=0)
    if (reference.expired_signals != fast.expired_signals
            or reference.pending_at_end != fast.pending_at_end
            or len(reference.equity) != len(minutes)):
        raise AssertionError("Canonical/fast M1 parity failed")
    previous = None
    for trade in reference.trades.itertuples(index=False):
        if previous is not None and trade.entry_at <= previous:
            raise AssertionError("One-slot overlap or same-instant reentry")
        previous = trade.closed_at
    trades = reference.trades
    if not np.isclose(float(trades.cost.sum()), FEE * len(trades), atol=1e-8, rtol=0):
        raise AssertionError("Fixed ALL-IN fee mismatch")
    booked = {}
    for trade in trades.itertuples(index=False):
        month = pd.Timestamp(trade.closed_at).tz_convert("UTC").strftime("%Y-%m")
        booked[month] = booked.get(month, 0.0) + float(trade.net_pnl)
    monthly = [{"month_utc": str(m), "net_usd_per_oz": booked.get(str(m), 0.0),
                "observed_m1_bars": int(n)}
               for m, n in observed_months.items()]
    monthly_risk = monthly_observed_m1_risk(minutes, reference.equity)
    if len(monthly_risk) != len(monthly):
        raise AssertionError("FAC025 monthly M1 risk count mismatch")
    for month, risk in zip(monthly, monthly_risk):
        if month["month_utc"] != risk["month_utc"] or month["observed_m1_bars"] != risk["observed_m1_equity_marks"]:
            raise AssertionError("FAC025 monthly M1 risk month/mark mismatch")
        month.update({key: value for key, value in risk.items() if key != "month_utc"})
    equity = np.r_[0., reference.equity.equity.to_numpy(dtype=float)]
    dd = float(np.max(np.maximum.accumulate(equity) - equity))
    return reference, {
        "status": "BID_REFERENCE_REPLAY_ONLY_NOT_SOURCE_VERIFIED_NOT_OOS",
        "frozen_policy": "FAC025-ENTRY-A",
        "independent_hypotheses": 1, "correlated_filter_specs": 72,
        "submitted_intents": len(signals), "shared_capacity_positions": 1,
        "filled_reference_trades": len(trades),
        "expired_signals": reference.expired_signals,
        "pending_signals": reference.pending_at_end,
        "fee_usd_per_oz_all_in": FEE, "fees_usd_per_oz": float(trades.cost.sum()),
        "monthly_utc_exit_net_usd_per_oz": monthly,
        "month_coverage": "EACH_MONTH_OBSERVED_NOT_FULL_SESSION_CERTIFIED",
        "monthly_m1_risk_scope": "BID_REFERENCE_OBSERVED_CLOSE_MARKS_NOT_INTRABAR_OR_AUTHENTICATED_BIDASK",
        "positive_months": sum(x["net_usd_per_oz"] > 0 for x in monthly),
        "worst_month_usd_per_oz": min(x["net_usd_per_oz"] for x in monthly),
        "max_observed_m1_close_equity_drawdown_usd_per_oz": dd,
        "reference_fast_parity_m1_marks": len(reference.equity),
        "source_authenticated": False, "paired_bidask_execution_verified": False,
        "original_gold_zip_backtests": 0, "independent_oos_verified": False,
        "approved_strategies": 0,
    }
