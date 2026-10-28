"""Check that frozen exported trades are a lossless view of executed trades.

This detects export drift even when monthly, weekly and annual sums agree.
It is not a broker execution or independent reference-ledger certification.
"""
from __future__ import annotations

from datetime import datetime
import math

import pandas as pd

FIELDS = (
    "strategy", "signal_at", "entry_at", "closed_at", "side",
    "entry_price", "exit_price", "stop", "target", "ounces",
    "gross_pnl", "cost", "net_pnl", "exit_reason", "gap_minutes",
)
TIMES = frozenset({"signal_at", "entry_at", "closed_at"})
INTEGERS = frozenset({"side", "gap_minutes"})
TEXT = frozenset({"strategy", "exit_reason"})


def verify_persisted_trade_ledger(executed: pd.DataFrame, exported: pd.DataFrame) -> None:
    """Require row-by-row 15-field parity against the actual in-memory executor.

    A report could change exit prices/timestamps without changing annual P/L
    or the UTC period bucket. Checking the output against itself is insufficient.
    """
    if not isinstance(executed, pd.DataFrame) or not isinstance(exported, pd.DataFrame):
        raise ValueError("Trade ledgers must be DataFrames")
    if len(executed) != len(exported):
        raise ValueError("Persisted trade ledger row count differs from execution")
    for label, frame in (("execution", executed), ("export", exported)):
        if frame.columns.has_duplicates or not set(FIELDS).issubset(frame.columns):
            raise ValueError(f"{label} trade ledger has missing/duplicate audit fields")
    if executed.empty:
        return
    for field in FIELDS:
        lhs, rhs = executed[field], exported[field]
        if field in TIMES:
            for raw in lhs:
                if not isinstance(raw, datetime) or pd.isna(raw) or raw.tzinfo is None:
                    raise ValueError(f"Execution trade has invalid UTC {field}")
            for raw in rhs:
                if not isinstance(raw, str):
                    raise ValueError(f"Export trade has invalid UTC {field}")
                try:
                    stamp = pd.Timestamp(raw)
                except (ValueError, TypeError, OverflowError) as exc:
                    raise ValueError(f"Export trade has invalid UTC {field}") from exc
                if pd.isna(stamp) or stamp.tzinfo is None:
                    raise ValueError(f"Export trade has invalid UTC {field}")
            try:
                l_ns = pd.to_datetime(lhs, utc=True).dt.as_unit("ns").astype("int64").to_numpy()
                r_ns = pd.to_datetime(rhs, utc=True).dt.as_unit("ns").astype("int64").to_numpy()
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError(f"Invalid trade {field} timestamp") from exc
            match = (l_ns == r_ns).all()
        elif field in TEXT:
            for series in (lhs, rhs):
                if any(not isinstance(v, str) or not v for v in series):
                    raise ValueError(f"Invalid trade {field} text")
            match = lhs.tolist() == rhs.tolist()
        elif field in INTEGERS:
            for series in (lhs, rhs):
                if not pd.api.types.is_integer_dtype(series.dtype) or pd.api.types.is_bool_dtype(series.dtype):
                    raise ValueError(f"Invalid trade {field} integer dtype")
            match = lhs.tolist() == rhs.tolist()
            if field == "side" and any(x not in (-1, 1) for x in lhs):
                raise ValueError("Invalid execution trade side")
            if field == "gap_minutes" and any(x < 0 for x in lhs):
                raise ValueError("Invalid execution gap minutes")
        else:
            for series in (lhs, rhs):
                if not pd.api.types.is_numeric_dtype(series.dtype) or pd.api.types.is_bool_dtype(series.dtype):
                    raise ValueError(f"Invalid trade {field} numeric dtype")
            left = lhs.to_numpy(dtype="float64")
            right = rhs.to_numpy(dtype="float64")
            if not (pd.notna(left).all() and pd.notna(right).all()
                    and all(math.isfinite(x) for x in left)
                    and all(math.isfinite(x) for x in right)):
                raise ValueError(f"Nonfinite trade {field}")
            match = (abs(left - right) <= 1e-7).all()
        if not match:
            raise ValueError(f"Persisted trade ledger differs from execution: {field}")

    # Matching execution/export rows are not enough: both could contain the
    # same corrupted accounting. Independently reconstruct each trade using
    # the FROZEN $0.40/oz all-in model. Never infer a valid fee from a total.
    for label, frame in (("execution", executed), ("export", exported)):
        for row in frame.itertuples(index=False):
            if row.ounces <= 0:
                raise ValueError(f"{label} trade has nonpositive ounces")
            # Original M1 OHLC and LimitOrder contracts forbid nonpositive
            # prices and reversed protective stop/target geometry. A matching
            # corruption in both ledgers must not bypass those invariants.
            if any(price <= 0 for price in (
                row.entry_price, row.exit_price, row.stop, row.target
            )):
                raise ValueError(f"{label} trade has nonpositive price")
            if ((row.side == 1 and not row.stop < row.entry_price < row.target)
                    or (row.side == -1 and not row.target < row.entry_price < row.stop)):
                raise ValueError(f"{label} trade has invalid stop/target geometry")
            expected_fee = 0.40 * row.ounces
            expected_gross = row.side * (row.exit_price - row.entry_price) * row.ounces
            if not math.isclose(row.cost, expected_fee, rel_tol=0, abs_tol=1e-9):
                raise ValueError(f"{label} trade fee differs from fixed $0.40/oz")
            if not math.isclose(row.gross_pnl, expected_gross, rel_tol=0, abs_tol=1e-7):
                raise ValueError(f"{label} trade gross P/L differs from price movement")
            if not math.isclose(row.net_pnl, row.gross_pnl - row.cost, rel_tol=0, abs_tol=1e-7):
                raise ValueError(f"{label} trade net P/L differs from gross less fee")
            if not (pd.Timestamp(row.signal_at) <= pd.Timestamp(row.entry_at)
                    <= pd.Timestamp(row.closed_at)):
                raise ValueError(f"{label} trade has reversed signal/entry/exit chronology")

            # The executor's named exit paths have distinct price contracts.
            # A ledger can match itself and balance financially while claiming
            # a target fill below TP or a stop fill better than the stop.
            # This verifies only price/reason consistency, NOT whether M1
            # quotes actually touched the claimed level.
            reason = row.exit_reason
            if reason in ("stop", "ambiguous_stop_first"):
                if not math.isclose(row.exit_price, row.stop, rel_tol=0, abs_tol=1e-7):
                    raise ValueError(f"{label} stop exit price differs from stop")
            elif reason in ("target", "open_target"):
                if not math.isclose(row.exit_price, row.target, rel_tol=0, abs_tol=1e-7):
                    raise ValueError(f"{label} target exit price differs from target")
            elif reason in ("open_stop", "gap_stop", "entry_open_beyond_stop"):
                # An adverse opening print may slip THROUGH the stop, never
                # improve the fill relative to that stop in this simulator.
                if row.side * (row.exit_price - row.stop) > 1e-7:
                    raise ValueError(f"{label} adverse open exit improved beyond stop")
            elif reason != "end_of_data":
                raise ValueError(f"{label} trade has unknown exit reason")
