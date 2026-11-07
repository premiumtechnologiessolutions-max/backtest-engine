"""FAC026: preregistered causal M15 compression breakout + H1 direction.

Research-only intent generator. No orders, fills, backtests or OOS claims.
All inputs are already closed, actually observed UTC candles and closed trades.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from itertools import product
import json
import math
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
M15 = timedelta(minutes=15)
H1 = timedelta(hours=1)
GRID = {
    "window": (8, 12),
    "compression": (0.65, 0.80),
    "h1_efficiency": (0.35, 0.55),
    "session": ((8, 12), (9, 13)),
    "daily_loss_halt": (2.0, 4.0),
}


def frozen_specs() -> list[dict]:
    """32 correlated specifications of ONE hypothesis; never 32 discoveries."""
    specs = []
    for window, compression, efficiency, session, halt in product(
        GRID["window"], GRID["compression"], GRID["h1_efficiency"],
        GRID["session"], GRID["daily_loss_halt"]
    ):
        params = {
            "window": window, "compression": compression,
            "h1_efficiency": efficiency, "session": list(session),
            "daily_loss_halt": halt,
        }
        payload = {"family": "NRF-FAC-026", "version": 1, "params": params}
        fingerprint = sha256(json.dumps(payload, sort_keys=True,
            separators=(",", ":")).encode("ascii")).hexdigest()
        specs.append({"params": params, "fingerprint": fingerprint})
    assert len(specs) == len({s["fingerprint"] for s in specs}) == 32
    return specs


def _utc(value: object, label: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        raise ValueError(f"{label}: timezone-aware UTC required")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{label}: UTC required")
    return value.astimezone(timezone.utc)


def _number(value: object, label: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label}: finite number required")
    if positive and value <= 0:
        raise ValueError(f"{label}: positive number required")
    return float(value)


def _bars(values: list[dict], *, step: timedelta, count: int,
          name: str, decision: datetime) -> list[dict]:
    if type(values) is not list:
        raise ValueError(f"{name}: expected list")
    expected = {"end_at", "open", "high", "low", "close", "observed_m1_count"}
    out = []
    previous = None
    for bar in values:
        if type(bar) is not dict or set(bar) != expected:
            raise ValueError(f"{name}: malformed candle")
        end = _utc(bar["end_at"], name)
        if end >= decision or (previous is not None and end <= previous):
            raise ValueError(f"{name}: future, same-instant or unordered candle")
        if end.second or end.microsecond or (end.minute % int(step.total_seconds() // 60)):
            raise ValueError(f"{name}: unaligned candle")
        if type(bar["observed_m1_count"]) is not int or not 0 <= bar["observed_m1_count"] <= count:
            raise ValueError(f"{name}: invalid observed M1 count")
        o, h, l, c = (_number(bar[k], f"{name} {k}", positive=True)
                      for k in ("open", "high", "low", "close"))
        if not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError(f"{name}: invalid OHLC")
        out.append({"end": end, "open": o, "high": h, "low": l,
                    "close": c, "count": bar["observed_m1_count"]})
        previous = end
    return out


def evaluate(signal_at: datetime, m15_bars: list[dict],
             h1_bars: list[dict], closed_trades: list[dict],
             *, spec: dict) -> dict:
    """Emit causal research intent; execution/one-slot capacity are NOT simulated."""
    now = _utc(signal_at, "signal_at")
    allowed = {s["fingerprint"]: s["params"] for s in frozen_specs()}
    if type(spec) is not dict or set(spec) != {"params", "fingerprint"}:
        raise ValueError("Unfrozen FAC026 specification")
    if spec["fingerprint"] not in allowed or spec["params"] != allowed[spec["fingerprint"]]:
        raise ValueError("Unfrozen FAC026 specification")
    p = spec["params"]
    m15 = _bars(m15_bars, step=M15, count=15, name="M15", decision=now)
    h1 = _bars(h1_bars, step=H1, count=60, name="H1", decision=now)
    if type(closed_trades) is not list:
        raise ValueError("Closed trade ledger must be a list")
    realized = 0.0
    previous = None
    day = now.astimezone(NY).date()
    for trade in closed_trades:
        if type(trade) is not dict or set(trade) != {"closed_at", "net_usd_per_oz"}:
            raise ValueError("Malformed closed trade")
        end = _utc(trade["closed_at"], "closed_at")
        net = _number(trade["net_usd_per_oz"], "net_usd_per_oz")
        if end >= now or (previous is not None and end < previous):
            raise ValueError("Future or unordered closed trade")
        if end.astimezone(NY).date() == day:
            realized += net
        previous = end
    if not math.isfinite(realized):
        raise ValueError("Nonfinite cumulative daily realized net")
    result = {
        "status": "BLOCKED", "reason": None, "side": None,
        "normalized_risk": None, "realized_today_usd_per_oz": round(realized, 8),
        "entry_policy": "NEXT_OBSERVED_M1_OPEN_WITHIN_60S_CANONICAL_REQUIRED",
        "execution": "RESEARCH_ONLY_NO_ORDERS",
        "hypothesis": "NRF-FAC-026",
    }
    def block(reason):
        result["reason"] = reason
        return result
    hour = now.astimezone(NY).hour
    if not p["session"][0] <= hour < p["session"][1]:
        return block("OUTSIDE_NY_SESSION")
    if realized <= -p["daily_loss_halt"]:
        return block("PREKNOWN_DAILY_LOSS_HALT")
    n = p["window"]
    if len(m15) < 2 * n + 1 or len(h1) < 3:
        return block("INSUFFICIENT_CONTEXT")
    context = m15[-(2 * n + 1):]
    hcontext = h1[-3:]
    if any(b["count"] != 15 for b in context) or any(b["count"] != 60 for b in hcontext):
        return block("INCOMPLETE_OBSERVED_M1")
    if any(b["end"] - a["end"] != M15 for a, b in zip(context, context[1:])):
        return block("M15_GAP")
    if any(b["end"] - a["end"] != H1 for a, b in zip(hcontext, hcontext[1:])):
        return block("H1_GAP")
    if now - context[-1]["end"] != timedelta(minutes=1):
        return block("STALE_OR_SAME_INSTANT_SIGNAL")
    if hcontext[-1]["end"] > context[-1]["end"]:
        return block("H1_NOT_PREKNOWN_AT_M15_CLOSE")
    baseline = context[:n]
    compressed = context[n:-1]
    trigger = context[-1]
    base_range = sum(b["high"] - b["low"] for b in baseline) / n
    comp_range = sum(b["high"] - b["low"] for b in compressed) / n
    if base_range <= 0 or comp_range > p["compression"] * base_range:
        return block("NO_PREKNOWN_VOLATILITY_COMPRESSION")
    long = trigger["close"] > max(b["high"] for b in compressed)
    short = trigger["close"] < min(b["low"] for b in compressed)
    if long == short:
        return block("NO_UNAMBIGUOUS_BREAKOUT")
    h_move = hcontext[-1]["close"] - hcontext[0]["open"]
    h_range = sum(b["high"] - b["low"] for b in hcontext)
    efficiency = abs(h_move) / h_range if h_range > 0 else 0.0
    side = 1 if long else -1
    if side * h_move <= 0 or efficiency < p["h1_efficiency"]:
        return block("H1_DIRECTION_EFFICIENCY_MISMATCH")
    risk = max(trigger["high"] - trigger["low"], trigger["close"] * 0.0004)
    normalized = risk / trigger["close"]
    if normalized > 0.002:
        return block("NORMALIZED_RISK_TOO_HIGH")
    result.update(status="ELIGIBLE_RESEARCH_INTENT_ONLY",
                  reason="PREKNOWN_FILTERS_PASS_NOT_A_TRADE",
                  side=side, normalized_risk=round(normalized, 12))
    return result
