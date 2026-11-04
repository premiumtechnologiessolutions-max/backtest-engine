"""Causal gold M1 + OpenBB/FRED research timeline; offline only.

Fuses validated original BID/ASK M1 close observations with frozen OpenBB
snapshots. Prevents the common hindsight mistake of treating a revised
economic series observed today as if known during an old gold backtest.

No broker connection, trading instruction, extrapolation, gap fill or
assertion of independent research acceptance is performed here.
"""
from __future__ import annotations

import re
from typing import Iterator

import pandas as pd

from .causal_stream_merge import CausalEvent, merge_causal_streams
from .data import PRICE_COLUMNS, fingerprint_loaded_m1, validate_loaded_m1
from .openbb_fred_snapshot import to_prospective_causal_events

_MINUTE_NS = 60_000_000_000
_MAX_BARS = 50_000
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def gold_m1_closed_events(frame: pd.DataFrame, *,
                          expected_loaded_fingerprint: str
                          ) -> tuple[CausalEvent, ...]:
    """Pin a bounded original M1 slice; OHLC is available at candle CLOSE.

    `expected_loaded_fingerprint` must come from independently retained
    source evidence; passing a hash computed from tampered input cannot prove
    the file was authentic. This function makes the conservative assumption
    that completed OHLC is observable at the next minute boundary, not earlier.
    """
    if (not isinstance(frame, pd.DataFrame) or
            not 1 <= len(frame) <= _MAX_BARS):
        raise ValueError("Gold M1 replay needs 1..50000 candles per chunk")
    if (type(expected_loaded_fingerprint) is not str
            or not _SHA.fullmatch(expected_loaded_fingerprint)):
        raise ValueError("Missing original loaded-M1 fingerprint")
    validate_loaded_m1(frame)
    fingerprint = fingerprint_loaded_m1(frame)
    if fingerprint != expected_loaded_fingerprint:
        raise ValueError("Observed M1 BID/ASK source differs from frozen fingerprint")
    prices = frame.loc[:, PRICE_COLUMNS].to_numpy(dtype=float, copy=True)
    opens_ns = frame.index.as_unit("ns").asi8
    result = []
    for seq, (opened, row) in enumerate(zip(opens_ns, prices)):
        event_at = int(opened)
        result.append(CausalEvent(
            source="gold", source_sha256=fingerprint,
            kind="closed_m1_bidask", event_at_ns=event_at,
            available_at_ns=event_at + _MINUTE_NS, sequence=seq,
            values=tuple(float(v) for v in row),
        ))
    return tuple(result)


def research_timeline(frame: pd.DataFrame, *,
                      expected_loaded_fingerprint: str,
                      fred_snapshot: dict | None = None,
                      through_ns: int | None = None
                      ) -> tuple[CausalEvent, ...]:
    """Merge M1 and frozen FRED read-only evidence in genuine known-at order.

    The OpenBB snapshot MUST remain excluded from any historical decision
    earlier than capture. No result is certified or allowed for broker orders.
    No missing gold quotes are manufactured.
    """
    streams = {
        "gold": gold_m1_closed_events(
            frame, expected_loaded_fingerprint=expected_loaded_fingerprint)
    }
    precedence = ("gold",)
    if fred_snapshot is not None:
        streams["openbb_fred"] = to_prospective_causal_events(fred_snapshot)
        # On equal known-at clocks, gold's closed-candle evidence is processed
        # before a newly captured macro snapshot, not retrospectively revised.
        precedence = ("gold", "openbb_fred")
    return tuple(merge_causal_streams(
        streams, precedence=precedence, through_ns=through_ns))


def research_state_at(frame: pd.DataFrame, *, expected_loaded_fingerprint: str,
                      decision_at: object, fred_snapshot: dict | None = None
                      ) -> dict:
    """Read-only decision-time diagnostic with explicit non-approval flags."""
    decision = pd.Timestamp(decision_at)
    if pd.isna(decision) or decision.tzinfo is None:
        raise ValueError("Decision must be timezone-aware")
    when_ns = decision.tz_convert("UTC").as_unit("ns").value
    gold, fred = None, None
    for event in research_timeline(
        frame, expected_loaded_fingerprint=expected_loaded_fingerprint,
        fred_snapshot=fred_snapshot, through_ns=when_ns
    ):
        if event.source == "gold":
            gold = event
        elif event.source == "openbb_fred":
            fred = event
    return {
        "decision_at_ns": when_ns,
        "last_gold_candle_known_at_ns": gold.available_at_ns if gold else None,
        "last_gold_bid_close": gold.values[3] if gold else None,
        "last_gold_ask_close": gold.values[7] if gold else None,
        "fred_last_observed_period_ns": fred.event_at_ns if fred else None,
        "fred_last_observed_value": fred.values[0] if fred else None,
        "fred_capture_known_at_ns": fred.available_at_ns if fred else None,
        "fred_historical_release_verified": False,
        "external_research_result_accepted": False,
        "live_trading_authorized": False,
    }
