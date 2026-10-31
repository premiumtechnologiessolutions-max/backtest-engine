"""Regression contracts for annual quote partitioning; gaps never imply fills."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import pytest

from scripts.liquidity_quote_segments import partition_execution_m1


@dataclass(frozen=True)
class Bar:
    time: datetime
    bid_open: float = 100.0
    bid_high: float = 101.0
    bid_low: float = 99.0
    bid_close: float = 100.0
    ask_open: float = 100.2
    ask_high: float = 101.2
    ask_low: float = 99.2
    ask_close: float = 100.2


def bar(minute):
    return Bar(datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minute))


def test_long_weekend_gap_is_recorded_not_interpolated():
    rows = [bar(0), bar(1), bar(60 * 72 + 2), bar(60 * 72 + 3)]
    segments, gaps = partition_execution_m1(iter(rows))
    assert [len(segment) for segment in segments] == [2, 2]
    assert sum(map(len, segments)) == len(rows)
    assert len(gaps) == 1
    assert gaps[0].missing_minutes == 60 * 72
    assert gaps[0].previous_time == rows[1].time
    assert gaps[0].next_time == rows[2].time
    assert segments[0][0] is rows[0] and segments[1][-1] is rows[-1]


@pytest.mark.parametrize("bad", [
    replace(bar(0), ask_open=None),
    replace(bar(0), ask_close=float("nan")),
    replace(bar(0), ask_high=float("inf")),
    replace(bar(0), bid_low=101.5),
    replace(bar(0), ask_low=98.0),
])
def test_any_invalid_quote_fails_entire_partition(bad):
    with pytest.raises((ValueError, TypeError)):
        partition_execution_m1([bar(0), replace(bad, time=bar(4).time)])


def test_non_utc_time_in_later_segment_rejected():
    shifted = replace(bar(4), time=bar(4).time.astimezone(timezone(timedelta(hours=2))))
    with pytest.raises(ValueError, match="UTC"):
        partition_execution_m1([bar(0), shifted])


def test_no_partial_output_on_invalid_last_segment():
    rows = [bar(0), bar(1), bar(5), replace(bar(6), ask_close=98.0)]
    with pytest.raises(ValueError, match="ASK"):
        partition_execution_m1(iter(rows))
