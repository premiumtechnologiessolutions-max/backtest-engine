"""Conservative XAUUSD M1 quote-gap catalogue.

These are classifications of timestamp *patterns*. They do not prove the
broker's historical trading hours, causes of outages, or executable quotes.
"""
from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

NY = ZoneInfo("America/New_York")


def _easter(year: int) -> date:
    """Gregorian Easter Sunday, used ONLY for calendar hints."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f, g = (b + 8) // 25, (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
    start = date(year, month, 1)
    return start + timedelta(days=(weekday - start.weekday()) % 7 + 7 * (nth - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    last = next_month - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def holiday_hints(year: int) -> dict[date, list[str]]:
    """Broad US calendar CANDIDATES, not a CME/spot-metals closure schedule."""
    pairs: list[tuple[date, str]] = [
        (_observed(date(year, 1, 1)), "New Year's Day (US)"),
        (_nth_weekday(year, 1, 0, 3), "Martin Luther King Jr. Day (US)"),
        (_nth_weekday(year, 2, 0, 3), "Presidents Day (US)"),
        (_easter(year) - timedelta(days=2), "Good Friday"),
        (_last_weekday(year, 5, 0), "Memorial Day (US)"),
        (_observed(date(year, 7, 4)), "Independence Day (US)"),
        (_nth_weekday(year, 9, 0, 1), "Labor Day (US)"),
        (_nth_weekday(year, 11, 3, 4), "Thanksgiving Day (US)"),
        (_observed(date(year, 12, 25)), "Christmas (US)"),
    ]
    if year >= 2021:
        pairs.append((_observed(date(year, 6, 19)), "Juneteenth (US)"))
    hints: dict[date, list[str]] = {}
    for when, name in pairs:
        hints.setdefault(when, []).append(name)
    return hints


def _holiday_overlap(previous: pd.Timestamp, next_open: pd.Timestamp) -> str:
    # Restrict to small date span; long data outages remain unknown.
    start = previous.tz_convert(NY).date()
    end = next_open.tz_convert(NY).date()
    if (end - start).days > 12:
        return ""
    names: set[str] = set()
    for year in range(start.year - 1, end.year + 2):
        for day, labels in holiday_hints(year).items():
            if start <= day <= end:
                names.update(labels)
    return "; ".join(sorted(names))


def classify_gap(previous: pd.Timestamp, next_open: pd.Timestamp) -> dict:
    """Classify one interval by NYC time and cautious holiday-calendar hints."""
    prev = pd.Timestamp(previous)
    nxt = pd.Timestamp(next_open)
    if prev.tzinfo is None or nxt.tzinfo is None:
        raise ValueError("Gap endpoints must be timezone aware")
    prev, nxt = prev.tz_convert("UTC"), nxt.tz_convert("UTC")
    if nxt <= prev:
        raise ValueError("Gap end must follow the previous candle")
    delta_min = (nxt - prev).total_seconds() / 60
    missing = delta_min - 1
    before, after = prev.tz_convert(NY), nxt.tz_convert(NY)
    classification = "unexplained_active_session"
    confidence = "low"
    hint = _holiday_overlap(prev, nxt)

    # Last Friday quote near the NY 17:00 close, first Sunday quote near 18:00.
    # This is a characteristic ~49h spot trading-week gap, not a broker contract.
    friday_close = before.weekday() == 4 and (
        (before.hour == 16 and before.minute >= 40) or before.hour == 17
    )
    sunday_open = after.weekday() == 6 and 17 <= after.hour <= 19
    weekend_span = 46 * 60 <= delta_min <= 54 * 60
    if friday_close and sunday_open and weekend_span:
        classification, confidence = "regular_weekend_pattern", "high_time_match"
    else:
        # Monday–Thursday (NY), typical NY 17–18 break, DST aware.
        daily_last = before.weekday() < 4 and (
            (before.hour == 16 and before.minute >= 40) or before.hour == 17
        )
        daily_next = before.date() == after.date() and (
            after.hour == 17 and after.minute >= 30 or after.hour == 18
        )
        if daily_last and daily_next and 20 <= delta_min <= 150:
            classification, confidence = "regular_daily_break_pattern", "high_time_match"
        elif hint:
            classification, confidence = "holiday_calendar_candidate", "calendar_only"
        elif friday_close or sunday_open or before.weekday() >= 5 or after.weekday() >= 5:
            classification, confidence = "nonstandard_weekend_window", "low"
        elif daily_last or before.hour == 17 or after.hour == 18:
            classification, confidence = "extended_rollover_window", "low"

    return {
        "last_seen_utc": prev.isoformat(),
        "next_seen_utc": nxt.isoformat(),
        "last_seen_new_york": before.isoformat(),
        "next_seen_new_york": after.isoformat(),
        "elapsed_minutes": int(round(delta_min)),
        "missing_minutes": int(round(missing)),
        "classification": classification,
        "confidence": confidence,
        "calendar_hints_not_verified": hint,
        "needs_review": confidence != "high_time_match",
    }


def classify_index_gaps(index: pd.DatetimeIndex, *, min_missing_minutes: int = 10) -> pd.DataFrame:
    """Produce only gaps with MORE than min_missing_minutes missing M1 bars."""
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("Expected a timezone-aware DatetimeIndex")
    if index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("Index must be sorted and unique")
    if min_missing_minutes < 0:
        raise ValueError("min_missing_minutes must be >= 0")
    cols = [
        "last_seen_utc", "next_seen_utc", "last_seen_new_york",
        "next_seen_new_york", "elapsed_minutes", "missing_minutes",
        "classification", "confidence", "calendar_hints_not_verified",
        "needs_review",
    ]
    delta = index.to_series().diff().dt.total_seconds().div(60)
    idx = delta[delta > min_missing_minutes + 1].index
    lookup = index.get_indexer(idx)
    rows = [classify_gap(index[i - 1], index[i]) for i in lookup]
    return pd.DataFrame.from_records(rows, columns=cols)
