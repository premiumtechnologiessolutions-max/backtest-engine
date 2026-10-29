"""Independent M1 source checks for non-slippage Limit executor exit labels.

These are quote-bar consistency checks, not tick ordering, broker fills,
spread, or proof that a strategy was profitable out of sample.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from numbers import Integral, Real
import numpy as np
import pandas as pd

from .executor_quote_contract import require_numeric_execution_ohlc

AUDITED_REASONS = frozenset({
    "stop", "ambiguous_stop_first", "target", "open_target", "end_of_data",
})
EPS = 1e-7


def verify_source_bar_exit_prices(m1: pd.DataFrame, trades: pd.DataFrame) -> dict[str, int]:
    """Verify reported stop/target/end-of-data exits against observed BID M1.

    This complements verify_source_open_exit_prices for adverse opening stops.
    It deliberately does not infer intraminute sequencing from OHLC.
    """
    require_numeric_execution_ohlc(m1)
    index = m1.index
    if (not isinstance(index, pd.DatetimeIndex) or index.empty
            or index.tz is None or str(index.tz) != "UTC"
            or index.hasnans or index.has_duplicates or not index.is_monotonic_increasing
            or (index.as_unit("ns").asi8 % 60_000_000_000 != 0).any()):
        raise ValueError("Source-bar audit requires sorted unique UTC minute opens")
    bars = m1[["o", "h", "l", "c"]].to_numpy(dtype=float)
    op, hi, lo, cl = (bars[:, k] for k in range(4))
    if (not np.isfinite(bars).all() or (bars <= 0).any()
            or (lo > np.minimum(op, cl)).any()
            or (hi < np.maximum(op, cl)).any()):
        raise ValueError("Source-bar audit requires finite positive valid OHLC")
    if not isinstance(trades, pd.DataFrame) or trades.columns.has_duplicates:
        raise ValueError("Source-bar audit requires trade DataFrame with unique columns")
    required = {"entry_at", "closed_at", "exit_price", "exit_reason", "side", "stop", "target"}
    if not required.issubset(trades.columns):
        raise ValueError("Source-bar audit missing trade fields")
    counts = {reason: 0 for reason in sorted(AUDITED_REASONS)}
    for row in trades.itertuples(index=False):
        reason = row.exit_reason
        if reason not in AUDITED_REASONS:
            continue
        for name in ("entry_at", "closed_at"):
            at = getattr(row, name)
            if (not isinstance(at, datetime) or pd.isna(at)
                    or at.tzinfo is None or at.utcoffset() != timedelta(0)):
                raise ValueError(f"Source-bar audit requires UTC-aware {name}")
        entry = pd.Timestamp(row.entry_at).tz_convert("UTC")
        closed = pd.Timestamp(row.closed_at).tz_convert("UTC")
        locations = index.get_indexer([entry, closed])
        if (locations < 0).any() or entry > closed:
            raise AssertionError("Source-bar exit/entry timestamp absent or reversed")
        position = int(locations[1])
        if (isinstance(row.side, (bool, np.bool_))
                or not isinstance(row.side, Integral) or row.side not in (-1, 1)):
            raise ValueError("Source-bar side must be integer +1/-1")
        for name in ("exit_price", "stop", "target"):
            value = getattr(row, name)
            if (isinstance(value, (bool, np.bool_))
                    or not isinstance(value, Real) or not np.isfinite(value) or value <= 0):
                raise ValueError(f"Source-bar {name} must be finite positive numeric")
        side = int(row.side)
        stop_touched = lo[position] <= row.stop + EPS if side == 1 else hi[position] >= row.stop - EPS
        target_touched = hi[position] >= row.target - EPS if side == 1 else lo[position] <= row.target + EPS
        if reason in ("stop", "ambiguous_stop_first"):
            if abs(row.exit_price - row.stop) > EPS or not stop_touched:
                raise AssertionError("Source-bar stop fill lacks matching stop and M1 touch")
            if (reason == "ambiguous_stop_first") != bool(target_touched):
                raise AssertionError("Source-bar stop ambiguity label disagrees with M1 range")
        elif reason == "target":
            if (entry == closed or abs(row.exit_price - row.target) > EPS
                    or not target_touched or stop_touched):
                raise AssertionError("Source-bar target exit lacks eligible unambiguous M1 touch")
        elif reason == "open_target":
            if (entry == closed or abs(row.exit_price - row.target) > EPS
                    or side * (op[position] - row.target) < -EPS):
                raise AssertionError("Source-bar open_target lacks favorable source M1 open")
        elif reason == "end_of_data":
            if (position != len(index) - 1 or abs(row.exit_price - cl[-1]) > EPS
                    or counts[reason]):
                raise AssertionError("Source-bar end_of_data differs from final M1 close")
        counts[reason] += 1
    return counts
