"""Independently check stop-at-open exits against observed M1 BID opens.

This is a narrow source-consistency audit, not tick execution verification.
It deliberately checks no intraminute stop/target touch or broker fill.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import math
from numbers import Integral, Real

import pandas as pd

OPEN_REASONS = frozenset({"open_stop", "gap_stop", "entry_open_beyond_stop"})
MINUTE = pd.Timedelta(minutes=1)


def verify_source_open_exit_prices(m1: pd.DataFrame, trades: pd.DataFrame) -> int:
    """Fail closed when an adverse open-stop exit disagrees with the source BID open.

    The engine's opening-stop paths execute at the first observed M1 BID open.
    `gap_stop` must follow a missing minute; `open_stop` must be contiguous;
    `entry_open_beyond_stop` must open and close on the same M1 timestamp.
    """
    if not isinstance(m1, pd.DataFrame) or not isinstance(m1.index, pd.DatetimeIndex):
        raise ValueError("Source-open audit requires M1 DatetimeIndex")
    index = m1.index
    if (index.empty or index.tz is None or str(index.tz) != "UTC"
            or index.hasnans or index.has_duplicates or not index.is_monotonic_increasing
            or (index.as_unit("ns").asi8 % 60_000_000_000 != 0).any()):
        raise ValueError("Source-open audit requires sorted unique UTC minute opens")
    if m1.columns.has_duplicates:
        raise ValueError("Source-open audit rejects duplicate M1 columns")
    if ("o" not in m1.columns
            or not pd.api.types.is_numeric_dtype(m1["o"].dtype)
            or pd.api.types.is_bool_dtype(m1["o"].dtype)):
        raise ValueError("Source-open audit requires numeric BID open")
    opens = m1["o"].to_numpy(dtype=float)
    if not all(math.isfinite(x) and x > 0 for x in opens):
        raise ValueError("Source-open audit requires finite positive BID opens")
    if not isinstance(trades, pd.DataFrame):
        raise ValueError("Source-open audit requires trade DataFrame")
    if trades.columns.has_duplicates:
        raise ValueError("Source-open audit requires unique trade columns")
    fields = {"entry_at", "closed_at", "exit_price", "exit_reason", "side", "stop"}
    if not fields.issubset(trades.columns):
        raise ValueError("Source-open audit missing trade fields")
    count = 0
    for row in trades.itertuples(index=False):
        reason = row.exit_reason
        if reason not in OPEN_REASONS:
            continue
        for label in ("entry_at", "closed_at"):
            value = getattr(row, label)
            if (not isinstance(value, datetime) or value.tzinfo is None
                    or value.utcoffset() != timedelta(0)):
                raise ValueError(f"Source-open audit requires UTC-aware {label}")
        entry = pd.Timestamp(row.entry_at).tz_convert("UTC")
        closed = pd.Timestamp(row.closed_at).tz_convert("UTC")
        entry_position, position = index.get_indexer([entry, closed])
        if entry_position < 0:
            raise AssertionError("Opening-stop entry timestamp missing from source M1")
        if position < 0:
            raise AssertionError("Opening-stop exit timestamp missing from source M1")
        if isinstance(row.side, bool) or not isinstance(row.side, Integral):
            raise ValueError("Opening-stop side must be integer")
        if row.side not in (-1, 1):
            raise ValueError("Opening-stop side must be +1/-1")
        if (isinstance(row.exit_price, bool) or not isinstance(row.exit_price, Real)
                or not math.isfinite(row.exit_price)):
            raise ValueError("Opening-stop exit price must be finite numeric")
        if (isinstance(row.stop, bool) or not isinstance(row.stop, Real)
                or not math.isfinite(row.stop) or row.stop <= 0):
            raise ValueError("Opening-stop stop must be finite positive numeric")
        if not math.isclose(float(row.exit_price), opens[position], rel_tol=0, abs_tol=1e-7):
            raise AssertionError("Opening-stop exit price differs from source M1 BID open")
        if row.side * (float(row.exit_price) - float(row.stop)) > 1e-7:
            raise AssertionError("Opening-stop source fill improved beyond protective stop")
        if reason == "entry_open_beyond_stop":
            if entry != closed:
                raise AssertionError("Entry-open stop must enter and close on same M1")
        else:
            if entry >= closed or position == 0:
                raise AssertionError("Old-position opening stop requires earlier observed entry")
            elapsed = index[position] - index[position - 1]
            if reason == "gap_stop" and elapsed <= MINUTE:
                raise AssertionError("gap_stop requires missing source M1 minutes")
            if reason == "open_stop" and elapsed != MINUTE:
                raise AssertionError("open_stop requires contiguous source M1")
        count += 1
    return count
