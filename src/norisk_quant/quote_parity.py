"""Fail-closed BID+ASK tick-to-M1 OHLC audit, NOT a tick execution model.

Input tick events must have genuine timestamp/sequence provenance; agreement of
aggregated OHLC cannot authenticate a feed or recover missing intraminute paths.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


_BID = ("o", "h", "l", "c")
_ASK = ("ao", "ah", "al", "ac")


def compare_bid_ask_ticks_to_m1(
    ticks: pd.DataFrame, minutes: pd.DataFrame, *, tolerance: float = 1e-6
) -> pd.DataFrame:
    """Compare BOTH quote sides on each source M1 minute, without filling gaps.

    ``both_quotes_match`` is False for missing tick minutes, even if no
    observed quote differs. An exact OHLC match does not prove tick completeness.
    All timestamps must be UTC-aware; M1 timestamps are minute-open aligned.
    """
    if (isinstance(tolerance, (bool, np.bool_)) or
            not isinstance(tolerance, (int, float, np.integer, np.floating)) or
            not math.isfinite(tolerance) or tolerance < 0):
        raise ValueError("tolerance must be finite and nonnegative")
    if ticks.empty or minutes.empty:
        raise ValueError("Tick and M1 datasets must be nonempty")
    for name, frame in (("ticks", ticks), ("M1", minutes)):
        if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
            raise ValueError(f"{name} requires timezone-aware DatetimeIndex")
        if (frame.index.hasnans or not frame.index.is_monotonic_increasing or
                str(frame.index.tz) != "UTC"):
            raise ValueError(f"{name} timestamps must be finite sorted UTC")
    if (minutes.index.has_duplicates or
            (minutes.index.as_unit("ns").asi8 % 60_000_000_000 != 0).any()):
        raise ValueError("M1 requires unique minute-aligned UTC opens")
    if not {"bid", "ask"}.issubset(ticks.columns):
        raise ValueError("Tick BID and ASK columns are required")
    if not set(_BID + _ASK).issubset(minutes.columns):
        raise ValueError("M1 BID and ASK OHLC columns are required")
    if ticks.index.has_duplicates:
        if "seq" not in ticks.columns:
            raise ValueError("Duplicate tick timestamps require source sequence")
        seq = pd.to_numeric(ticks["seq"], errors="coerce").to_numpy(dtype=float)
        if (not np.isfinite(seq).all() or (seq % 1 != 0).any() or
                pd.MultiIndex.from_arrays([ticks.index, seq]).has_duplicates):
            raise ValueError("Invalid duplicate tick timestamp/sequence")
        # No reordering by price or guessed intraminute event sequence.
        for _, group in pd.Series(seq, index=ticks.index).groupby(level=0, sort=False):
            if len(group) > 1 and not (np.diff(group.to_numpy()) > 0).all():
                raise ValueError("Duplicate tick sequence must already be sorted")
    quotes = ticks[["bid", "ask"]].to_numpy(dtype=float)
    if (not np.isfinite(quotes).all() or (quotes <= 0).any() or
            (quotes[:, 1] < quotes[:, 0]).any()):
        raise ValueError("Invalid tick BID/ASK quotes")
    bars = minutes[list(_BID + _ASK)].to_numpy(dtype=float)
    if not np.isfinite(bars).all() or (bars <= 0).any():
        raise ValueError("Invalid BID/ASK M1 OHLC")
    for offset in (0, 4):
        o, h, l, c = bars[:, offset:offset + 4].T
        if ((h < np.maximum(o, c)) | (l > np.minimum(o, c))).any():
            raise ValueError("Invalid BID/ASK M1 OHLC")
    if (bars[:, 4:] < bars[:, :4]).any():
        raise ValueError("ASK M1 OHLC cannot be below corresponding BID OHLC")

    bid = ticks["bid"].resample("1min").ohlc()
    ask = ticks["ask"].resample("1min").ohlc()
    bid.columns = _BID
    ask.columns = _ASK
    observed = pd.concat([bid, ask], axis=1).reindex(minutes.index)
    tick_present = observed["o"].notna() & observed["ao"].notna()
    diff = (minutes[list(_BID + _ASK)] - observed).abs()
    bid_diff = diff[list(_BID)].max(axis=1, skipna=False)
    ask_diff = diff[list(_ASK)].max(axis=1, skipna=False)
    bid_mismatch = tick_present & bid_diff.gt(tolerance)
    ask_mismatch = tick_present & ask_diff.gt(tolerance)
    both_match = tick_present & ~bid_mismatch & ~ask_mismatch
    status = np.select(
        [~tick_present, bid_mismatch | ask_mismatch],
        ["NO_TICKS", "QUOTE_MISMATCH"], default="MATCHED_OBSERVED_OHLC"
    )
    return pd.DataFrame({
        "tick_present": tick_present.astype(bool),
        "bid_max_abs_diff": bid_diff,
        "ask_max_abs_diff": ask_diff,
        "bid_mismatch": bid_mismatch.astype(bool),
        "ask_mismatch": ask_mismatch.astype(bool),
        "both_quotes_match": both_match.astype(bool),
        "status": status,
    }, index=minutes.index)


def summarize_bid_ask_parity(report: pd.DataFrame) -> dict:
    """A strict audit passes only when every requested M1 has both matching sides."""
    required = {"tick_present", "bid_mismatch", "ask_mismatch", "both_quotes_match"}
    if report.empty or not required.issubset(report.columns):
        raise ValueError("Nonempty quote parity report required")
    count = len(report)
    present = int(report["tick_present"].sum())
    matching = int(report["both_quotes_match"].sum())
    mismatching = int((report["bid_mismatch"] | report["ask_mismatch"]).sum())
    return {
        "status": "PASSED_OBSERVED_OHLC_ONLY" if matching == count else "FAILED_OR_INCOMPLETE",
        "source_m1_minutes": count,
        "observed_tick_minutes": present,
        "missing_tick_minutes": count - present,
        "quote_mismatch_minutes": mismatching,
        "both_sides_matching_minutes": matching,
        "coverage_fraction": present / count,
        "warning": "Matching OHLC cannot prove tick feed completeness, fill accuracy, or broker authenticity.",
    }
