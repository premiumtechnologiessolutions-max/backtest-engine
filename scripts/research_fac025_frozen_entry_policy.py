"""FAC025-ENTRY-A: preregistered research intent, NOT an executable portfolio.

A single fixed M15 liquidity sweep/reclaim with strictly older completed H1
trend. Never reads next-minute entry prices, generates fills, or claims P/L.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math

try:
    from scripts.research_fac025_frozen_receipt_bridge import evaluate_frozen_fac025_receipts
    from scripts.research_fac025_observed_m15 import reconstruct_observed_m15
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    from research_fac025_frozen_receipt_bridge import evaluate_frozen_fac025_receipts
    from research_fac025_observed_m15 import reconstruct_observed_m15

POLICY = {
    "id": "FAC025-ENTRY-A", "version": 1, "sweep_prior_m15_bars": 4,
    "h1_completed_bars": 2, "min_stop_fraction": "0.0004",
    "max_stop_fraction": "0.0015", "reward_multiple": "1.50",
    "max_entry_delay_seconds": 60, "capacity": 1,
    "fee_usd_per_oz": "0.40",
}
POLICY_SHA256 = "f4378cdee27d247864fad77895137c709b7fb674b27c3f2aef77c16419015eee"
QUARTER = timedelta(minutes=15)
HOUR = timedelta(hours=1)


def frozen_policy_fingerprint() -> str:
    digest = sha256(json.dumps(POLICY, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True).encode("ascii")).hexdigest()
    if digest != POLICY_SHA256:
        raise ValueError("FAC025-ENTRY-A frozen policy mutated")
    return digest


def propose_frozen_entry(signal_at: datetime, paired_m1: list[dict],
                         canonical_trades: list[dict], *, spec_id: str,
                         parameters: dict, fingerprint: str) -> dict:
    """Return only an auditable prospective *intent*, never a trade or fill.

    Caller-provided BID/ASK receipts and closed trades pass the existing frozen
    gate first. Missing M1 or H1 context fail closed. Any actual entry requires
    a separately verified next eligible observed open <=60 seconds later and
    a one-position shared-capacity executor (not provided here).
    """
    policy_hash = frozen_policy_fingerprint()
    receipt = evaluate_frozen_fac025_receipts(
        signal_at, paired_m1, canonical_trades, spec_id=spec_id,
        parameters=parameters, fingerprint=fingerprint)
    base = {
        "status": "NO_INTENT", "reason": "FILTER_BLOCKED",
        "frozen_entry_policy": POLICY["id"], "policy_sha256": policy_hash,
        "filter_spec_id": spec_id, "filter_fingerprint": fingerprint,
        "entry_price": "N/A", "stop_price": "N/A", "target_price": "N/A",
        "monthly_net_pnl_usd_per_oz": "N/A",
        "floating_m1_drawdown_usd_per_oz": "N/A",
        "capacity_verified": False, "source_authenticated": False,
        "execution": "RESEARCH_INTENT_ONLY_NO_FILLS_NO_ORDERS",
    }
    if receipt["gate"]["status"] != "ELIGIBLE_RESEARCH_ONLY":
        base["reason"] = receipt["gate"]["reason"]
        return base
    bid_rows = [{"open_at": r["open_at"], "open": r["bid_open"],
                 "high": r["bid_high"], "low": r["bid_low"],
                 "close": r["bid_close"]} for r in paired_m1]
    bars = reconstruct_observed_m15(bid_rows, signal_at, lookback=16)
    if len(bars) < 9:
        base["reason"] = "INSUFFICIENT_COMPLETE_M15_H1_CONTEXT"
        return base
    latest = bars[-1]
    last_five = bars[-5:]
    if (any(b["observed_m1_count"] != 15 for b in last_five)
            or any(b["end_at"] - a["end_at"] != QUARTER
                   for a, b in zip(last_five, last_five[1:]))):
        base["reason"] = "INCOMPLETE_SWEEP_CONTEXT"
        return base
    # H1 must finish before the START of the candidate M15; never use the
    # H1 bar containing the signal, even if its timestamp looks complete.
    last_start = latest["end_at"] - QUARTER
    h1_cutoff = last_start.replace(minute=0, second=0, microsecond=0)
    by_end = {b["end_at"]: b for b in bars}
    h1_closes = []
    for h1_end in (h1_cutoff - HOUR, h1_cutoff):
        group = [by_end.get(h1_end - QUARTER * k) for k in (3, 2, 1, 0)]
        if any(b is None or b["observed_m1_count"] != 15 for b in group):
            base["reason"] = "INCOMPLETE_H1_CONTEXT"
            return base
        h1_closes.append(group[-1]["close"])
    previous = last_five[:-1]
    support = min(b["low"] for b in previous)
    resistance = max(b["high"] for b in previous)
    bullish = latest["low"] < support < latest["close"] and h1_closes[1] > h1_closes[0]
    bearish = latest["high"] > resistance > latest["close"] and h1_closes[1] < h1_closes[0]
    if bullish == bearish:
        base["reason"] = "NO_UNAMBIGUOUS_SWEEP_WITH_PRIOR_H1_TREND"
        return base
    side = "BUY" if bullish else "SELL"
    close = latest["close"]
    wick_distance = close - latest["low"] if bullish else latest["high"] - close
    risk = max(wick_distance, close * float(POLICY["min_stop_fraction"]))
    if not math.isfinite(risk) or risk > close * float(POLICY["max_stop_fraction"]):
        base["reason"] = "NORMALIZED_STOP_RISK_EXCEEDED"
        return base
    if type(signal_at) is not datetime or signal_at.tzinfo is None or signal_at.utcoffset() != timedelta(0):
        raise ValueError("Signal timestamp must be UTC-aware")
    base.update({
        "status": "RESEARCH_INTENT_ONLY", "reason": "FROZEN_SWEEP_H1_CONFIRMED",
        "side": side, "signal_at": signal_at.astimezone(timezone.utc).isoformat(),
        "entry_deadline_utc": (signal_at + timedelta(seconds=60)).isoformat(),
        "max_entry_delay_seconds": 60, "shared_capacity_slots": 1,
        "risk_distance_usd_per_oz": round(risk, 8),
        "target_distance_usd_per_oz": round(risk * 1.5, 8),
        "fee_usd_per_oz_all_in_roundtrip": 0.40,
        "risk_sizing": "UNDEFINED_NO_POSITION_SIZE",
    })
    return base
