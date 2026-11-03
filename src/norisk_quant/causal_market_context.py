"""Point-in-time macro/news context for research, never retrospective hindsight.

A known event *date* or revised present-day FRED observation is insufficient
for intraday historical trading. A usable value needs the precise release time,
first-observed time and immutable vintage. No guessed timestamps or news scores.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
import pandas as pd

from .oanda_readonly import utc_timestamp

NAME = re.compile(r"[A-Za-z][A-Za-z0-9_./:-]{1,79}\Z")
KINDS = frozenset({"policy_rate", "news_score", "economic_actual"})
CURRENCIES = frozenset({"USD", "EUR", "GBP", "AUD", "NZD", "CAD", "CHF", "JPY", "XAU"})


@dataclass(frozen=True)
class Observation:
    key: str
    kind: str
    value: float
    released_at: pd.Timestamp
    first_seen_at: pd.Timestamp
    vintage: str
    source: str

    def __post_init__(self) -> None:
        if (not isinstance(self.key, str) or not NAME.fullmatch(self.key)
                or self.kind not in KINDS
                or not isinstance(self.source, str) or not NAME.fullmatch(self.source)
                or not isinstance(self.vintage, str) or not NAME.fullmatch(self.vintage)
                or isinstance(self.value, bool)
                or not isinstance(self.value, (int, float))
                or not math.isfinite(self.value)):
            raise ValueError("Invalid point-in-time macro observation")
        released, seen = utc_timestamp(self.released_at), utc_timestamp(self.first_seen_at)
        if seen < released:
            raise ValueError("A published value cannot be seen before release")
        object.__setattr__(self, "released_at", released)
        object.__setattr__(self, "first_seen_at", seen)


@dataclass(frozen=True)
class ScheduledEvent:
    event_id: str
    currency: str
    announced_at: pd.Timestamp
    scheduled_at: pd.Timestamp
    impact: str
    source: str

    def __post_init__(self) -> None:
        if (not isinstance(self.event_id, str) or not NAME.fullmatch(self.event_id)
                or self.currency not in CURRENCIES
                or self.impact not in ("low", "medium", "high")
                or not isinstance(self.source, str) or not NAME.fullmatch(self.source)):
            raise ValueError("Invalid news schedule")
        announced, scheduled = utc_timestamp(self.announced_at), utc_timestamp(self.scheduled_at)
        if announced > scheduled:
            raise ValueError("Schedule was only announced after its event")
        object.__setattr__(self, "announced_at", announced)
        object.__setattr__(self, "scheduled_at", scheduled)


def as_of(observations: tuple[Observation, ...], decision_at: object) -> dict[str, Observation]:
    """Last actually known vintage per series; never use a future revision."""
    now = utc_timestamp(decision_at)
    latest = {}
    for obs in observations:
        if not isinstance(obs, Observation):
            raise ValueError("Macro data must use validated Observation records")
        if obs.first_seen_at > now:
            continue
        previous = latest.get(obs.key)
        if previous is None or (obs.first_seen_at, obs.vintage) > (
                previous.first_seen_at, previous.vintage):
            latest[obs.key] = obs
    return latest


def news_blackout(schedules: tuple[ScheduledEvent, ...], instrument: str,
                  at: object, before_minutes: int = 15,
                  after_minutes: int = 15) -> tuple[str, ...]:
    """Known-in-advance high-impact event veto, not an economic prediction."""
    if (type(before_minutes) is not int or type(after_minutes) is not int
            or not 0 <= before_minutes <= 1440
            or not 0 <= after_minutes <= 1440):
        raise ValueError("Invalid frozen blackout limits")
    currencies = instrument.split("_")
    if len(currencies) != 2 or any(c not in CURRENCIES for c in currencies):
        raise ValueError("Invalid instrument for macro calendar")
    now = utc_timestamp(at)
    blocked = []
    for event in schedules:
        if not isinstance(event, ScheduledEvent):
            raise ValueError("Invalid scheduled event")
        if (event.impact == "high" and event.currency in currencies
                and event.announced_at <= now
                and event.scheduled_at - pd.Timedelta(minutes=before_minutes) <= now
                <= event.scheduled_at + pd.Timedelta(minutes=after_minutes)):
            blocked.append(event.event_id)
    return tuple(sorted(set(blocked)))


def observations_from_json(items: object) -> tuple[Observation, ...]:
    if type(items) is not list or len(items) > 100_000:
        raise ValueError("Macro observations require bounded JSON list")
    result = []
    for entry in items:
        if type(entry) is not dict or set(entry) != set(Observation.__dataclass_fields__):
            raise ValueError("Macro observation fields require explicit provenance")
        result.append(Observation(**entry))
    return tuple(result)


def schedules_from_json(items: object) -> tuple[ScheduledEvent, ...]:
    if type(items) is not list or len(items) > 100_000:
        raise ValueError("News schedule requires bounded JSON list")
    result = []
    for entry in items:
        if type(entry) is not dict or set(entry) != set(ScheduledEvent.__dataclass_fields__):
            raise ValueError("News schedule needs announcement and event times")
        result.append(ScheduledEvent(**entry))
    return tuple(result)
