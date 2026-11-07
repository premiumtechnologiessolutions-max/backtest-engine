"""FAC025 BID-reference monthly M1 equity risk audit (research only).

Observed CLOSE-mark risk, not intrabar worst excursion, authenticated BID/ASK
execution, full market-session coverage, or prospective OOS evidence.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def monthly_observed_m1_risk(observed_minutes: pd.DataFrame, equity: pd.DataFrame) -> list[dict]:
    """Recompute per-UTC-month drawdown using only actual M1 equity marks.

    First-month peak baseline is zero. Later months start from the last
    observed previous-month equity; absent minutes are never interpolated.
    Month-local peaks reset and differ from continuous global drawdown.
    """
    if not isinstance(observed_minutes, pd.DataFrame) or not isinstance(equity, pd.DataFrame):
        raise ValueError("Observed M1 and equity must be DataFrames")
    idx, marks = observed_minutes.index, equity.index
    if (not isinstance(idx, pd.DatetimeIndex) or not isinstance(marks, pd.DatetimeIndex)
            or idx.tz is None or marks.tz is None or idx.hasnans or marks.hasnans
            or not idx.is_unique or not marks.is_unique or not idx.is_monotonic_increasing
            or not marks.is_monotonic_increasing or len(idx) == 0):
        raise ValueError("Observed M1/equity require nonempty sorted unique timezone-aware indexes")
    observed_utc = idx.tz_convert("UTC").as_unit("ns")
    marks_utc = marks.tz_convert("UTC").as_unit("ns")
    if not observed_utc.equals(marks_utc):
        raise ValueError("Equity marks must match each observed M1 open exactly; no fabricated minutes")
    if np.any(observed_utc.asi8 % 60_000_000_000):
        raise ValueError("Observed M1 must be aligned to UTC minute opens")
    required = ("equity", "realized_pnl", "floating_pnl")
    if not equity.columns.is_unique:
        raise ValueError("Duplicate M1 equity column labels")
    if not set(required).issubset(equity.columns):
        raise ValueError("Missing M1 equity/realized/floating columns")
    for column in required:
        dtype = equity[column].dtype
        if not (pd.api.types.is_integer_dtype(dtype) or pd.api.types.is_float_dtype(dtype)):
            raise ValueError(f"M1 {column} must have a real numeric dtype, not coerced text/bool/complex")
    try:
        values = equity[list(required)].to_numpy(dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError("Non-numeric M1 equity values") from exc
    if not np.isfinite(values).all() or not np.allclose(
            values[:, 0], values[:, 1] + values[:, 2], rtol=0, atol=1e-8):
        raise ValueError("Non-finite or unreconciled M1 equity values")
    months = observed_utc.tz_localize(None).to_period("M")
    out = []
    previous_close = 0.0
    start = 0
    for end in np.r_[np.flatnonzero(months[1:] != months[:-1]) + 1, len(months)]:
        series = values[start:end, 0]
        peak = float(previous_close)
        drawdown = 0.0
        for point in series:
            peak = max(peak, float(point))
            drawdown = max(drawdown, peak - float(point))
        out.append({
            "month_utc": str(months[start]),
            "observed_m1_equity_marks": int(end - start),
            "month_local_max_observed_m1_close_drawdown_usd_per_oz": float(drawdown),
        })
        previous_close = float(series[-1])
        start = int(end)
    return out
