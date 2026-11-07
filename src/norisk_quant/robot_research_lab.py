"""Bounded multi-robot, multi-asset *signal research*, with a shared arbiter.

No order placement, broker fills, P/L, leverage, margin, position sizing, or
profitability claims. Robots produce immutable next-open INTENTS for separate
certified execution research. Intent is not an order and must not be sent live.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from collections import defaultdict

import pandas as pd
import numpy as np

from . import causal_market_context as _context_module
from . import oanda_readonly as _oanda_module
from .causal_market_context import (
    Observation, ScheduledEvent, as_of, news_blackout,
)
from .oanda_readonly import ClosedCandle, INSTRUMENT

ROBOT_ID = re.compile(r"[a-z][a-z0-9_-]{2,63}\Z")
FAMILIES = frozenset({"momentum", "mean_reversion", "rate_differential"})
STATUS = "RESEARCH_INTENTS_ONLY_NOT_EXECUTED_NOT_OOS"


@dataclass(frozen=True)
class RobotSpec:
    robot_id: str
    instrument: str
    family: str
    lookback: int
    threshold: float
    max_spread_quote: float
    cooldown_minutes: int
    stop_distance_quote: float
    reward_risk: float = 1.5

    def __post_init__(self) -> None:
        if (not ROBOT_ID.fullmatch(self.robot_id)
                or not INSTRUMENT.fullmatch(self.instrument)
                or self.family not in FAMILIES
                or type(self.lookback) is not int or not 2 <= self.lookback <= 240
                or type(self.cooldown_minutes) is not int
                or not 0 <= self.cooldown_minutes <= 1440):
            raise ValueError("Invalid frozen research robot specification")
        for field in ("threshold", "max_spread_quote", "stop_distance_quote", "reward_risk"):
            value = getattr(self, field)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value <= 0):
                raise ValueError(f"Invalid research robot {field}")
        if self.family == "rate_differential" and self.instrument.startswith("XAU_"):
            raise ValueError("Gold has no XAU policy rate for differential hypothesis")


def robots_from_json(items: object) -> tuple[RobotSpec, ...]:
    if type(items) is not list or not 1 <= len(items) <= 32:
        raise ValueError("Research lab supports 1..32 frozen robots per batch")
    result = []
    for item in items:
        if type(item) is not dict or not (
                set(item) in (set(RobotSpec.__dataclass_fields__),
                              set(RobotSpec.__dataclass_fields__) - {"reward_risk"})):
            raise ValueError("Robot JSON fields must match frozen contract")
        result.append(RobotSpec(**item))
    if len({r.robot_id for r in result}) != len(result):
        raise ValueError("Duplicate research robot ID")
    return tuple(result)


def _candidate(robot: RobotSpec, candles: tuple[ClosedCandle, ...],
               index: int, snapshot: dict[str, Observation]) -> int:
    if robot.family == "rate_differential":
        base, quote = robot.instrument.split("_")
        first, second = snapshot.get(f"policy_rate_{base}"), snapshot.get(f"policy_rate_{quote}")
        if (first is None or second is None
                or first.kind != "policy_rate" or second.kind != "policy_rate"):
            return 0
        difference = first.value - second.value
        return 1 if difference >= robot.threshold else (
            -1 if difference <= -robot.threshold else 0)
    # Only the last completed close and earlier completed closes are used.
    current = candles[index].bid_c
    anchor = candles[index - robot.lookback].bid_c
    change = (current - anchor) / anchor
    side = 1 if change >= robot.threshold else (
        -1 if change <= -robot.threshold else 0)
    return -side if robot.family == "mean_reversion" else side


def evaluate_robots(candles_by_instrument: dict[str, tuple[ClosedCandle, ...]],
                    robots: tuple[RobotSpec, ...],
                    observations: tuple[Observation, ...] = (),
                    schedules: tuple[ScheduledEvent, ...] = (),
                    *, news_before_minutes: int = 15,
                    news_after_minutes: int = 15,
                    max_intents: int = 10000) -> dict:
    """Emit deterministic, causally justified intents, never orders.

    One accepted robot per instrument and closed candle; opposite robot
    directions cause ABSTAIN. A gap in any lookback minute invalidates that
    candidate. No look-ahead to a later OANDA complete candle.
    """
    if (not isinstance(candles_by_instrument, dict)
            or len(candles_by_instrument) > 12
            or not isinstance(robots, tuple) or not 1 <= len(robots) <= 32
            or type(max_intents) is not int or not 1 <= max_intents <= 100000):
        raise ValueError("Invalid bounded research job")
    if len({r.robot_id for r in robots}) != len(robots):
        raise ValueError("Duplicate research robot")
    if any(not isinstance(r, RobotSpec) for r in robots):
        raise ValueError("Invalid frozen robot")
    if any(r.instrument not in candles_by_instrument for r in robots):
        raise ValueError("Missing robot instrument candles")
    results = defaultdict(int)
    proposed: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for instrument, candles in sorted(candles_by_instrument.items()):
        if not INSTRUMENT.fullmatch(instrument) or not isinstance(candles, tuple):
            raise ValueError("Invalid frozen candle partition")
        if not 1 <= len(candles) <= 5000:
            raise ValueError("Bounded M1 candle partition required")
        if any(not isinstance(c, ClosedCandle) or c.instrument != instrument
               for c in candles):
            raise ValueError("Candle instrument mismatch")
        if any(candles[i].opened_at <= candles[i - 1].opened_at
               for i in range(1, len(candles))):
            raise ValueError("Unsorted/duplicate research candles")
        for robot in sorted((r for r in robots if r.instrument == instrument),
                            key=lambda r: r.robot_id):
            last_accepted = None
            for i in range(robot.lookback, len(candles)):
                now = candles[i].known_at
                # Do not bridge closures, weekends or a missing quote interval.
                window = candles[i - robot.lookback:i + 1]
                if any(window[j].opened_at - window[j - 1].opened_at
                       != pd.Timedelta(minutes=1) for j in range(1, len(window))):
                    results["blocked_gap"] += 1
                    continue
                if last_accepted is not None and (
                    now - last_accepted < pd.Timedelta(minutes=robot.cooldown_minutes)
                ):
                    results["blocked_cooldown"] += 1
                    continue
                if candles[i].spread_close > robot.max_spread_quote:
                    results["blocked_spread"] += 1
                    continue
                if news_blackout(schedules, instrument, now,
                                 news_before_minutes, news_after_minutes):
                    results["blocked_scheduled_news"] += 1
                    continue
                snapshot = as_of(observations, now)
                side = _candidate(robot, candles, i, snapshot)
                if side == 0:
                    results["no_signal_or_macro_unavailable"] += 1
                    continue
                # Decision is at candle CLOSE. A later open is NOT known here.
                proposed[(str(now), instrument)].append({
                    "robot_id": robot.robot_id, "family": robot.family,
                    "instrument": instrument, "confirmed_at": str(now),
                    "side": side,
                    "stop_distance_quote": float(robot.stop_distance_quote),
                    "target_distance_quote": float(
                        robot.stop_distance_quote * robot.reward_risk),
                    "status": "INTENT_ONLY_NEXT_OPEN_NOT_EXECUTED",
                    "macro_keys_known": sorted(snapshot),
                })
                last_accepted = now
                results["proposed"] += 1
                if results["proposed"] > max_intents:
                    raise ValueError("Research intent budget exhausted")
    accepted = []
    for key in sorted(proposed):
        candidates = proposed[key]
        if len({x["side"] for x in candidates}) > 1:
            results["conflict_abstain"] += len(candidates)
            continue
        accepted.append(sorted(candidates, key=lambda x: x["robot_id"])[0])
        results["duplicate_same_direction_suppressed"] += len(candidates) - 1
    def digest_input(value) -> str:
        return hashlib.sha256(json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False, default=str,
        ).encode("utf-8")).hexdigest()

    # A report digest without its source quotes is not an experiment identity:
    # two different price histories may produce identical intents and counters.
    # Bind EVERY observed BA M1 OHLC, first-seen macro vintage, schedule
    # revision and governing filter to this immutable research evidence.
    quote_sources = {
        instrument: [
            [c.instrument, c.opened_at.isoformat(), c.bid_o, c.bid_h,
             c.bid_l, c.bid_c, c.ask_o, c.ask_h, c.ask_l, c.ask_c,
             c.volume]
            for c in candles
        ]
        for instrument, candles in sorted(candles_by_instrument.items())
    }
    input_hashes = {
        "closed_m1_bidask_sha256": digest_input(quote_sources),
        "macro_vintages_sha256": digest_input([asdict(o) for o in observations]),
        "news_revisions_sha256": digest_input([asdict(e) for e in schedules]),
        "decision_policy_sha256": digest_input({
            "news_before_minutes": news_before_minutes,
            "news_after_minutes": news_after_minutes,
            "max_intents": max_intents,
            "robots": [asdict(r) for r in sorted(robots, key=lambda r: r.robot_id)],
            "intent_engine_contract": "NRFX_MULTI_ASSET_RESEARCH_INTENTS_V1",
        }),
        # Digest actual imported source bytes, not an unverified environment
        # label. These are reproducibility identifiers, NOT code signatures.
        "engine_sources_sha256": digest_input({
            "robot_research_lab": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "causal_market_context": hashlib.sha256(
                Path(_context_module.__file__).read_bytes()).hexdigest(),
            "oanda_readonly": hashlib.sha256(
                Path(_oanda_module.__file__).read_bytes()).hexdigest(),
        }),
        "runtime_versions_sha256": digest_input({
            "python": [sys.version_info.major, sys.version_info.minor,
                       sys.version_info.micro],
            "pandas": pd.__version__,
            "numpy": np.__version__,
        }),
    }
    payload = {
        "schema": "NRFX_MULTI_ASSET_RESEARCH_INTENTS_V1",
        "status": STATUS, "broker_order_placement_enabled": False,
        "execution_model": "NONE_INTENTS_NOT_FILLS",
        "research_profitability_proven": False, "independent_oos_proven": False,
        "all_in_cost_model": "NOT_APPLIED_NO_TRADES",
        "instruments": sorted(candles_by_instrument),
        "input_hashes": input_hashes,
        "robots": [asdict(r) for r in sorted(robots, key=lambda r: r.robot_id)],
        "counters": dict(sorted(results.items())),
        "intents": accepted,
    }
    payload["manifest_sha256"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    return payload
