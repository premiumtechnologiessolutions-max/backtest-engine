from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import pytest
from scripts.liquidity_quote_segments import partition_execution_m1

@dataclass(frozen=True)
class Bar:
    time: datetime
    bid_open: float = 100.
    bid_high: float = 101.
    bid_low: float = 99.
    bid_close: float = 100.
    ask_open: float = 100.2
    ask_high: float = 101.2
    ask_low: float = 99.2
    ask_close: float = 100.2

def b(n):
    return Bar(datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=n))

def test_gaps_split_and_count_absent_minutes():
    segments, gaps = partition_execution_m1(iter([b(0), b(1), b(5), b(6), b(10)]))
    assert [len(x) for x in segments] == [2, 2, 1]
    assert [g.missing_minutes for g in gaps] == [3, 3]
    assert gaps[0].previous_time == b(1).time
    assert gaps[0].next_time == b(5).time

def test_no_gap():
    segments, gaps = partition_execution_m1([b(0), b(1)])
    assert len(segments) == 1 and gaps == []

def test_empty():
    assert partition_execution_m1(iter(())) == ([], [])

@pytest.mark.parametrize('rows', [[b(1), b(1)], [b(2), b(1)]])
def test_nonmonotonic_rejected(rows):
    with pytest.raises(ValueError, match='duplicate|unsorted'):
        partition_execution_m1(rows)

def test_invalid_quote_in_later_segment_rejected():
    with pytest.raises(ValueError, match='ASK'):
        partition_execution_m1([b(0), replace(b(5), ask_low=98.)])

def test_subminute_gap_rejected():
    with pytest.raises(ValueError, match='minute-aligned'):
        partition_execution_m1([b(0), replace(b(5), time=b(5).time + timedelta(seconds=1))])
