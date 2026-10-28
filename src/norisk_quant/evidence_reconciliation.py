"""Independent UTC trade-exit allocation checks for frozen research ledgers.

Does not validate broker fills, profitability, provenance or OOS status.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
import re

TOLERANCE = 1e-6
MONTH_LABEL = re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])\Z")
WEEK_LABEL = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}/[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


def _validate_period_label(kind: str, label: str) -> None:
    """Check canonical UTC report period labels, including empty periods."""
    if kind == "month":
        if not MONTH_LABEL.fullmatch(label):
            raise ValueError("Invalid UTC monthly period label")
        try:
            date.fromisoformat(label + "-01")
        except ValueError as exc:
            raise ValueError("Invalid UTC monthly period label") from exc
        return
    if not WEEK_LABEL.fullmatch(label):
        raise ValueError("Invalid UTC weekly period label")
    start_raw, end_raw = label.split("/")
    try:
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
    except ValueError as exc:
        raise ValueError("Invalid UTC weekly period label") from exc
    if start.weekday() != 0 or end.weekday() != 6 or end - start != timedelta(days=6):
        raise ValueError("Weekly period must run Monday through Sunday UTC")



def _amount(value: object) -> float:
    if type(value) not in (str, int, float):
        raise ValueError("Invalid period numeric value")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError("Invalid period numeric value") from exc
    if not math.isfinite(number):
        raise ValueError("Nonfinite period numeric value")
    return number


def _count(value: object) -> int:
    if type(value) is int and value >= 0:
        return value
    if type(value) is str and value.isascii() and (value == "0" or
            (value.isdigit() and value[0] != "0")):
        return int(value)
    raise ValueError("Invalid period trade count")


def verify_exit_periods(monthly: list[dict], weekly: list[dict], trades: list[dict]) -> None:
    """Reject period shifts that net aggregate accounting cannot detect.

    Official report._periods groups by UTC close month and W-SUN week.
    Every recorded month/week must match its individual exits exactly.
    """
    groups: dict[str, dict[str, list[float]]] = {"month": {}, "week": {}}
    for trade in trades:
        raw = trade.get("closed_at")
        if not isinstance(raw, str):
            raise ValueError("Missing UTC trade close timestamp")
        try:
            closed = datetime.fromisoformat(raw)
        except (ValueError, OverflowError) as exc:
            raise ValueError("Invalid UTC trade close timestamp") from exc
        if closed.tzinfo is None or closed.utcoffset() != timedelta(0):
            raise ValueError("Trade close timestamp must be UTC")
        utc = closed.astimezone(timezone.utc)
        monday = utc.date() - timedelta(days=utc.weekday())
        sunday = monday + timedelta(days=6)
        labels = {"month": utc.strftime("%Y-%m"),
                  "week": f"{monday.isoformat()}/{sunday.isoformat()}"}
        net = _amount(trade.get("net_pnl"))
        cost = _amount(trade.get("cost"))
        if cost < 0:
            raise ValueError("Negative trade cost")
        for kind, label in labels.items():
            totals = groups[kind].setdefault(label, [0, 0.0, 0.0])
            totals[0] += 1
            totals[1] += net
            totals[2] += cost

    for kind, rows in (("month", monthly), ("week", weekly)):
        seen: set[str] = set()
        for row in rows:
            label = row.get("period")
            if not isinstance(label, str) or label in seen:
                raise ValueError("Duplicate or invalid accounting period")
            _validate_period_label(kind, label)
            seen.add(label)
            expected = groups[kind].get(label, [0, 0.0, 0.0])
            observed = [_count(row.get("trades")), _amount(row.get("net_pnl")),
                        _amount(row.get("total_cost"))]
            if (observed[0] != expected[0] or
                    abs(observed[1] - expected[1]) > TOLERANCE or
                    abs(observed[2] - expected[2]) > TOLERANCE):
                raise ValueError("Trade exit allocation disagrees with period ledger")
        if groups[kind].keys() - seen:
            raise ValueError("Trade exit outside reported periods")
