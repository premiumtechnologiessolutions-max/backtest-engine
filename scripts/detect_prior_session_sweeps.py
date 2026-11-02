"""Causal, research-only prior-session sweep/reclaim signal detector.

Input is completed UTC M1 BID OHLC bars. This module deliberately emits signals,
not fills, performance claims, or executable orders. It must not be used for live trading.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math


@dataclass(frozen=True)
class Bar:
    timestamp: datetime  # UTC minute OPEN; bar is available at timestamp + 1 minute
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class SweepSignal:
    confirmed_at: datetime  # UTC; no earlier than bar CLOSE
    side: str
    swept_level: float
    extreme: float
    session_date: str


def detect_prior_utc_day_sweeps(bars, *, min_sweep_usd=0.50):
    """One signal per direction per UTC day, after sweep then close reclaim.

    Prior UTC day must contain exactly 1440 contiguous minute bars. Any missing
    bar in current day resets pending sweeps; no signals across discontinuities.
    Only completed bars are consumed, and no same-bar sweep/reclaim is allowed.
    """
    if isinstance(min_sweep_usd, bool) or not isinstance(min_sweep_usd, (int, float)) or not math.isfinite(min_sweep_usd) or min_sweep_usd <= 0:
        raise ValueError("min_sweep_usd must be finite and positive")
    bars = list(bars)
    previous = None
    days = {}
    for b in bars:
        if not isinstance(b.timestamp, datetime):
            raise ValueError("timestamps must be datetime instances")
        if b.timestamp.tzinfo is None or b.timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamps must be UTC aware")
        if b.timestamp.second or b.timestamp.microsecond:
            raise ValueError("timestamps must be minute aligned")
        if previous is not None and b.timestamp <= previous:
            raise ValueError("timestamps must be strictly increasing")
        previous = b.timestamp
        vals = (b.open, b.high, b.low, b.close)
        if not all(not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in vals):
            raise ValueError("prices must be positive finite numbers")
        if b.high < max(b.open, b.close, b.low) or b.low > min(b.open, b.close, b.high):
            raise ValueError("invalid OHLC envelope")
        days.setdefault(b.timestamp.date(), []).append(b)

    signals = []
    for day in sorted(days):
        prior = day - timedelta(days=1)
        prev = days.get(prior, [])
        curr = days[day]
        if len(prev) != 1440 or any(
            prev[i].timestamp - prev[i-1].timestamp != timedelta(minutes=1)
            for i in range(1, len(prev))
        ):
            continue
        prior_high = max(b.high for b in prev)
        prior_low = min(b.low for b in prev)
        pending_high = pending_low = None
        emitted = set()
        last = None
        for b in curr:
            if last is not None and b.timestamp - last != timedelta(minutes=1):
                pending_high = pending_low = None
            last = b.timestamp
            # Reclaim only from an earlier completed bar. Pending state is
            # inspected before registering sweeps from the current bar.
            # The confirming bar is completed at signal time; its wick may
            # extend the sweep extreme and must not be omitted from risk geometry.
            sell_reclaim = pending_high is not None and "SELL" not in emitted and b.close < prior_high
            buy_reclaim = pending_low is not None and "BUY" not in emitted and b.close > prior_low
            # A single completed bar cannot establish the ordering of two
            # opposite pending reclaims. Fail closed for both directions.
            if sell_reclaim and buy_reclaim:
                emitted.update(("SELL", "BUY"))
            elif sell_reclaim:
                signals.append(SweepSignal(b.timestamp + timedelta(minutes=1), "SELL",
                                           prior_high, max(pending_high, b.high), day.isoformat()))
                emitted.add("SELL")
            elif buy_reclaim:
                signals.append(SweepSignal(b.timestamp + timedelta(minutes=1), "BUY",
                                           prior_low, min(pending_low, b.low), day.isoformat()))
                emitted.add("BUY")
            if b.high >= prior_high + min_sweep_usd and "SELL" not in emitted:
                pending_high = max(pending_high or b.high, b.high)
            if b.low <= prior_low - min_sweep_usd and "BUY" not in emitted:
                pending_low = min(pending_low if pending_low is not None else b.low, b.low)
    return signals
