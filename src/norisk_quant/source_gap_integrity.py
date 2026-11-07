"""Independent reconciliation of persisted trade gap_minutes against source M1.

Only counts absent observed minute opens while a position was alive.
Missing quotes are not proof of an exchange closure or a broker outage.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from numbers import Integral

import numpy as np
import pandas as pd

MINUTE_NS = 60_000_000_000


def verify_source_gap_minutes(m1: pd.DataFrame, trades: pd.DataFrame) -> int:
    """Verify every recorded gap_minutes using the original observed UTC index.

    The gap preceding a new entry is excluded. All missing minutes between
    an observed entry and a later observed exit (including the exit bar)
    are included, matching the Limit executor's position.gap_minutes.
    """
    if not isinstance(m1, pd.DataFrame) or not isinstance(m1.index, pd.DatetimeIndex):
        raise ValueError("Gap audit requires source M1 DatetimeIndex")
    index = m1.index
    if (index.empty or index.tz is None or str(index.tz) != "UTC"
            or index.hasnans or index.has_duplicates
            or not index.is_monotonic_increasing):
        raise ValueError("Gap audit requires sorted unique UTC minute opens")
    stamps = index.as_unit("ns").asi8
    if (stamps % MINUTE_NS != 0).any():
        raise ValueError("Gap audit requires minute-aligned source timestamps")
    elapsed = np.diff(stamps)
    if (elapsed <= 0).any() or (elapsed % MINUTE_NS != 0).any():
        raise ValueError("Gap audit requires strictly increasing whole-minute bars")
    missing = elapsed // MINUTE_NS - 1
    cumulative = np.zeros(len(index), dtype=np.int64)
    cumulative[1:] = np.cumsum(missing, dtype=np.int64)
    if not isinstance(trades, pd.DataFrame) or trades.columns.has_duplicates:
        raise ValueError("Gap audit requires a trade DataFrame with unique columns")
    if not {"entry_at", "closed_at", "gap_minutes"}.issubset(trades.columns):
        raise ValueError("Gap audit missing trade fields")
    for row in trades.itertuples(index=False):
        for name in ("entry_at", "closed_at"):
            value = getattr(row, name)
            if (not isinstance(value, datetime) or pd.isna(value)
                    or value.tzinfo is None or value.utcoffset() != timedelta(0)):
                raise ValueError(f"Gap audit requires UTC-aware {name}")
        entry, closed = index.get_indexer([
            pd.Timestamp(row.entry_at).tz_convert("UTC"),
            pd.Timestamp(row.closed_at).tz_convert("UTC"),
        ])
        if entry < 0 or closed < entry:
            raise AssertionError("Gap audit entry/exit absent or reversed")
        actual = row.gap_minutes
        if (isinstance(actual, (bool, np.bool_)) or not isinstance(actual, Integral)
                or actual < 0):
            raise ValueError("Gap audit requires nonnegative integer gap_minutes")
        expected = int(cumulative[closed] - cumulative[entry])
        if int(actual) != expected:
            raise AssertionError(
                "Gap audit missing-minute count differs from source M1: "
                f"reported={int(actual)}, expected={expected}"
            )
    return len(trades)
