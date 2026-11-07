"""Conservative, read-only risk evidence from modeled M1 portfolio equity.

This measures OBSERVED research equity marks, not intrabar broker equity.
A gap in the original M1 timeline is never assumed to be a safe flat period.
This module does not run market strategies, create orders or approve outcomes.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RiskLimits:
    max_observed_peak_drawdown_usd: float
    max_observed_intraday_drawdown_usd: float

    def __post_init__(self) -> None:
        for value in (self.max_observed_peak_drawdown_usd,
                      self.max_observed_intraday_drawdown_usd):
            if (isinstance(value, (bool, np.bool_))
                    or not isinstance(value, Real)
                    or not isfinite(float(value)) or value <= 0):
                raise ValueError("Risk limits require finite positive USD values")


def observed_risk_evidence(equity: pd.DataFrame,
                           limits: RiskLimits | None = None) -> dict:
    """Audit observed M1 equity using strict chronology and optional budgets.

    Missing minutes can be legitimate closures; they still make unseen
    drawdowns unknown. A passing result is never equivalent to broker
    execution, tick evidence, OOS validation or profitability certification.
    """
    if not isinstance(equity, pd.DataFrame) or equity.empty or "equity" not in equity:
        raise ValueError("Nonempty observed portfolio equity required")
    index = equity.index
    if (not isinstance(index, pd.DatetimeIndex)
            or index.tz is None or str(index.tz) != "UTC"
            or index.hasnans or index.has_duplicates
            or not index.is_monotonic_increasing):
        raise ValueError("Risk equity timestamps must be unique ascending UTC")
    timestamps = index.as_unit("ns").asi8
    if (timestamps % 60_000_000_000 != 0).any():
        raise ValueError("Risk equity requires whole M1 candle-open timestamps")
    column = equity["equity"]
    if (not pd.api.types.is_numeric_dtype(column.dtype)
            or pd.api.types.is_bool_dtype(column.dtype)
            or pd.api.types.is_complex_dtype(column.dtype)):
        raise ValueError("Risk equity amounts must be real numeric values")
    values = column.to_numpy(dtype=float, copy=True)
    if not np.isfinite(values).all():
        raise ValueError("Risk equity contains nonfinite modeled balances")
    if limits is not None and not isinstance(limits, RiskLimits):
        raise ValueError("Expected frozen RiskLimits")
    gaps = np.diff(timestamps)
    if (gaps <= 0).any():
        raise ValueError("Risk equity time must increase")
    missing = sum(max(0, int(gap // 60_000_000_000) - 1) for gap in gaps)
    peak = np.maximum.accumulate(np.maximum(values, 0.0))
    global_drawdown = float(np.max(peak - values))
    worst_day = 0.0
    prev_day = None
    prev_close = 0.0
    prev_ts = None
    day_count = 0
    for day, group in column.groupby(index.normalize()):
        times = group.index.as_unit("ns").asi8
        data = group.to_numpy(dtype=float)
        # An uninterrupted midnight carries the previous observed equity
        # into the new day's start. After a quote gap we do NOT invent that
        # the last known equity was also the new day's opening balance.
        if prev_day is None:
            anchor = 0.0  # frozen research portfolio starts at zero P/L
        elif prev_ts is not None and times[0] - prev_ts == 60_000_000_000:
            anchor = prev_close
        else:
            anchor = float(data[0])  # first new observed mark after unknown gap
        daily_peaks = np.maximum.accumulate(
            np.maximum(data, anchor))
        worst_day = max(worst_day, float(np.max(daily_peaks - data)))
        prev_day = day
        prev_close = float(data[-1])
        prev_ts = int(times[-1])
        day_count += 1
    breached = False
    if limits is not None:
        breached = (
            global_drawdown > limits.max_observed_peak_drawdown_usd
            or worst_day > limits.max_observed_intraday_drawdown_usd
        )
    status = ("OBSERVED_RISK_LIMIT_BREACH" if breached else
              "OBSERVED_ONLY_GAPPED_UNCERTIFIED" if missing > 0 else
              "OBSERVED_ONLY_NOT_BROKER_VALIDATED")
    return {
        "schema": "NRFX_OBSERVED_PORTFOLIO_RISK_V1",
        "status": status,
        "equity_points": int(len(values)), "utc_days_observed": day_count,
        "unobserved_minutes_between_marks": int(missing),
        "gaps_between_marks": int(np.count_nonzero(gaps > 60_000_000_000)),
        "max_observed_peak_drawdown_usd": global_drawdown,
        "max_observed_intraday_drawdown_usd": worst_day,
        "observed_limit_breached": bool(breached),
        "risk_limits_supplied": limits is not None,
        "actual_intrabar_drawdown_unknown": True,
        "market_data_gap_is_not_proof_of_corruption": True,
        "broker_equity_reconciled": False,
        "independent_research_result_accepted": False,
        "live_trading_authorized": False,
    }
