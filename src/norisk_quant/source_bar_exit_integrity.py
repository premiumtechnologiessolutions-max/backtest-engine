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
    "open_stop", "gap_stop", "entry_open_beyond_stop",
})
EPS = 1e-7


def verify_source_bar_exit_prices(m1: pd.DataFrame, trades: pd.DataFrame) -> dict[str, int]:
    """Verify all Limit stop/target/end-of-data exits against observed BID M1.

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
    required = {"entry_at", "closed_at", "entry_price", "exit_price", "exit_reason", "side", "stop", "target"}
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
        entry_position = int(locations[0])
        # A source-bar exit audit cannot certify a trade whose LIMIT entry
        # never touched the observed entry candle. Validate the actual
        # persisted limit price, not merely the reported entry timestamp.
        entry_price = row.entry_price
        if (isinstance(entry_price, (bool, np.bool_))
                or not isinstance(entry_price, Real)
                or not np.isfinite(entry_price) or entry_price <= 0):
            raise ValueError("Source-bar entry_price must be finite positive numeric")
        if side == 1:
            if not row.stop < entry_price < row.target:
                raise AssertionError("Source-bar BUY requires stop < entry < target")
            if lo[entry_position] > entry_price + EPS:
                raise AssertionError("Source-bar BUY limit entry was not touched")
        else:
            if not row.target < entry_price < row.stop:
                raise AssertionError("Source-bar SELL requires target < entry < stop")
            if hi[entry_position] < entry_price - EPS:
                raise AssertionError("Source-bar SELL limit entry was not touched")
        # A correct exit on the reported close bar is insufficient: the
        # position must also have survived every earlier observed M1 bar.
        # The entry minute may defer a target (unknown intrabar ordering),
        # but a touched stop ALWAYS closes the new position on that minute.
        if position > entry_position:
            entry_stop = (
                lo[entry_position] <= row.stop + EPS if side == 1
                else hi[entry_position] >= row.stop - EPS
            )
            if entry_stop:
                raise AssertionError("Source-bar position survived entry-minute stop")
            # On every subsequent minute BEFORE the recorded exit, the
            # executor processes both open and intrabar stop/target touches.
            # A touch of either bound must have closed the position already.
            earlier = slice(entry_position + 1, position)
            if side == 1:
                premature = (lo[earlier] <= row.stop + EPS) | (
                    hi[earlier] >= row.target - EPS
                )
            else:
                premature = (hi[earlier] >= row.stop - EPS) | (
                    lo[earlier] <= row.target + EPS
                )
            if premature.any():
                raise AssertionError("Source-bar position survived an earlier eligible exit")
        # The limit executor processes an existing position's opening BID
        # before any intrabar high/low touch.  An adverse opening stop must
        # be labelled open_stop/gap_stop (or entry_open_beyond_stop for a
        # newly filled limit), and a favorable opening target is open_target.
        # A fabricated intrabar label must not pass merely because the
        # remainder of the M1 bar later touches the reported stop/target.
        if reason in ("stop", "ambiguous_stop_first", "target"):
            if side * (op[position] - row.stop) <= EPS:
                raise AssertionError(
                    "Source-bar intrabar exit conflicts with opening stop priority"
                )
            if side * (op[position] - row.target) >= -EPS:
                raise AssertionError(
                    "Source-bar intrabar exit conflicts with opening target priority"
                )
        stop_touched = lo[position] <= row.stop + EPS if side == 1 else hi[position] >= row.stop - EPS
        target_touched = hi[position] >= row.target - EPS if side == 1 else lo[position] <= row.target + EPS
        if reason in ("open_stop", "gap_stop", "entry_open_beyond_stop"):
            # The narrow source-open audit checks the recorded opening fill.
            # This full-OHLC audit ALSO checks survival of all earlier bars:
            # a matching later open cannot excuse an already-hit stop/target.
            if abs(row.exit_price - op[position]) > EPS:
                raise AssertionError("Source-bar opening stop differs from observed BID open")
            if side * (op[position] - row.stop) > EPS:
                raise AssertionError("Source-bar opening stop is favorable to protective stop")
            if reason == "entry_open_beyond_stop":
                if entry_position != position:
                    raise AssertionError("Source-bar entry-open stop must close on entry minute")
            else:
                if entry_position >= position or position == 0:
                    raise AssertionError("Source-bar old-position opening stop requires earlier entry")
                gap = index[position] - index[position - 1]
                if reason == "gap_stop" and gap <= pd.Timedelta(minutes=1):
                    raise AssertionError("Source-bar gap_stop requires missing source minutes")
                if reason == "open_stop" and gap != pd.Timedelta(minutes=1):
                    raise AssertionError("Source-bar open_stop requires contiguous source minutes")
        elif reason in ("stop", "ambiguous_stop_first"):
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
            # End-of-data is reached only if the executor did not exit on
            # the final bar. A same-minute limit entry may defer its TP, but
            # never a stop. An older position cannot defer either bound.
            if stop_touched or (entry_position < position and target_touched):
                raise AssertionError("Source-bar end_of_data skipped final-minute exit")
        counts[reason] += 1
    return counts
