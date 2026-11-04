"""Deterministic causal merge of immutable research event streams.

Design reviewed against NautilusTrader pinned source:
crates/data/src/replay/iterator.rs and crates/backtest/src/data_iterator.rs.
This is an independently implemented, bounded Python research adapter, NOT
a verbatim port, a broker execution event loop, or a result acceptance gate.
"""
from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
import re
from collections.abc import Iterable, Iterator, Mapping

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE = re.compile(r"[a-z][a-z0-9_]{1,47}\Z")
_KIND = re.compile(r"[a-z][a-z0-9_]{1,47}\Z")


def _clock(value: int, field: str) -> None:
    if type(value) is not int or not 0 <= value < 2**63:
        raise ValueError(f"Invalid nanosecond clock: {field}")


@dataclass(frozen=True, slots=True)
class CausalEvent:
    """Research observation with a separate event time and knowledge time.

    A closed M1 candle's available_at_ns must reflect when the candle became
    observable, not its opening timestamp. For macro/news use first-seen time.
    """
    source: str
    source_sha256: str
    kind: str
    event_at_ns: int
    available_at_ns: int
    sequence: int
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if (type(self.source) is not str or not _SOURCE.fullmatch(self.source)
                or type(self.kind) is not str or not _KIND.fullmatch(self.kind)
                or type(self.source_sha256) is not str
                or not _SHA.fullmatch(self.source_sha256)):
            raise ValueError("Invalid causal research event identity")
        _clock(self.event_at_ns, "event_at_ns")
        _clock(self.available_at_ns, "available_at_ns")
        if self.available_at_ns < self.event_at_ns:
            raise ValueError("Research event cannot be known before it occurred")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("Invalid event sequence")
        if (type(self.values) is not tuple or not 1 <= len(self.values) <= 32
                or any(type(value) not in (int, float)
                       or not math.isfinite(value) for value in self.values)):
            raise ValueError("Causal values must be bounded finite numbers")


def merge_causal_streams(
    streams: Mapping[str, Iterable[CausalEvent]], *,
    precedence: tuple[str, ...] | None = None,
    through_ns: int | None = None,
) -> Iterator[CausalEvent]:
    """Yield events in first-known order across at most 32 named streams.

    Equal-known-time priorities dominate event date, and are deterministic,
    rather than dependent on mapping insertion order. Historical FRED period
    dates cannot reorder data ahead of same-time closed M1 evidence. Each feed must arrive in nondecreasing availability order
    and strictly increasing sequence order; malformed feeds fail closed.
    Never feed this generator to a live trading engine. To publish a verified
    result, stage ALL output and independently reconcile its source bytes.
    """
    if type(streams) is not dict or not 1 <= len(streams) <= 32:
        raise ValueError("Require 1..32 named research streams")
    if any(type(name) is not str or not _SOURCE.fullmatch(name)
           for name in streams):
        raise ValueError("Unsafe research stream name")
    if precedence is None:
        ordered = tuple(sorted(streams))
    else:
        if (type(precedence) is not tuple or len(precedence) != len(streams)
                or set(precedence) != set(streams)):
            raise ValueError("Precedence must name every stream exactly once")
        ordered = precedence
    if through_ns is not None:
        _clock(through_ns, "through_ns")
    readers = {name: iter(streams[name]) for name in ordered}
    prior: dict[str, tuple[int, int, int, str]] = {}
    frontier: list[tuple[int, int, int, int, CausalEvent]] = []

    def push(name: str, priority: int) -> None:
        try:
            event = next(readers[name])
        except StopIteration:
            return
        if type(event) is not CausalEvent or event.source != name:
            raise ValueError("Mismatched research source/event type")
        previous = prior.get(name)
        if previous is not None:
            last_available, last_event, last_sequence, last_sha = previous
            if (event.sequence <= last_sequence
                    or event.available_at_ns < last_available
                    or (event.available_at_ns == last_available
                        and event.event_at_ns < last_event)
                    or event.source_sha256 != last_sha):
                raise ValueError("Out-of-order, replayed or source-drifted data")
        prior[name] = (event.available_at_ns, event.event_at_ns,
                       event.sequence, event.source_sha256)
        heapq.heappush(frontier, (event.available_at_ns, priority,
                                  event.event_at_ns, event.sequence, event))

    for priority, name in enumerate(ordered):
        push(name, priority)
    while frontier:
        available, priority, _, _, event = heapq.heappop(frontier)
        if through_ns is not None and available > through_ns:
            return
        yield event
        push(ordered[priority], priority)
