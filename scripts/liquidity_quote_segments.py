"""Partition chronological M1 quotes at missing minutes; never synthesize fills.

Each returned segment has passed the independent execution-grade quote gate.
Gap records describe absent quote minutes, NOT verified market closures.
"""
from dataclasses import dataclass
from datetime import timedelta

from scripts.liquidity_sweep_execution_quotes import require_execution_grade_m1


@dataclass(frozen=True)
class QuoteGap:
    previous_time: object
    next_time: object
    missing_minutes: int


def partition_execution_m1(bars):
    """Return (contiguous_segments, quote_gaps), preserving original rows.

    Reject duplicates, reverse ordering and off-grid gaps. Validate every
    segment before returning any results. No cross-gap position carry implied.
    """
    rows = list(bars)
    if not rows:
        return [], []
    segments, gaps = [], []
    current = [rows[0]]
    for row in rows[1:]:
        delta = row.time - current[-1].time
        if delta <= timedelta(0):
            raise ValueError('unsorted or duplicate M1')
        if delta != timedelta(minutes=1):
            if delta.total_seconds() % 60:
                raise ValueError('M1 gap must be minute-aligned')
            segments.append(require_execution_grade_m1(current))
            gaps.append(QuoteGap(current[-1].time, row.time,
                                 int(delta.total_seconds() // 60) - 1))
            current = []
        current.append(row)
    segments.append(require_execution_grade_m1(current))
    return segments, gaps
