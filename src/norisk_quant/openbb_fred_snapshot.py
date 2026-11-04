"""Read-only OpenBB/FRED snapshot adapter with strict prospective causality.

Uses upstream OpenBB QueryExecutor/FredSeries when installed. That upstream
fetcher drops FRED realtime-start/end vintage fields; these snapshots MUST NOT
be used as historically available observations in old XAUUSD backtests.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
import re
from typing import Any

import pandas as pd

from .causal_stream_merge import CausalEvent
from .oanda_readonly import utc_timestamp

SCHEMA = "NRFX_OPENBB_FRED_CAPTURE_V1"
UPSTREAM_COMMIT = "2a392e890f6eb1f0f4e3a71742720af8f056333a"
_SYMBOL = re.compile(r"[A-Z][A-Z0-9_]{0,31}\Z")
_MAX_ROWS = 5000


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _checksum(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _day(value: str) -> date:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("FRED dates must be canonical YYYY-MM-DD")
    d = date.fromisoformat(value)
    if d.isoformat() != value:
        raise ValueError("Invalid FRED date")
    return d


def _records(raw: Any, symbol: str) -> list[dict]:
    """Validate OpenBB native AnnotatedResult or Pydantic data rows."""
    if hasattr(raw, "result") and not isinstance(raw, (list, dict)):
        raw = raw.result
    if type(raw) is not list or len(raw) > _MAX_ROWS:
        raise ValueError("FRED returned malformed/oversized result")
    rows = []
    prior = None
    for obj in raw:
        if hasattr(obj, "model_dump") and callable(obj.model_dump):
            item = obj.model_dump(mode="json")
        elif type(obj) is dict:
            item = obj
        else:
            raise ValueError("Unknown FRED row model")
        if type(item) is not dict or set(item) != {"date", symbol}:
            raise ValueError("FRED result requires date and one requested series")
        at = item["date"]
        if isinstance(at, date) and not isinstance(at, pd.Timestamp):
            at = at.isoformat()
        day = _day(at)
        if prior is not None and day <= prior:
            raise ValueError("FRED observations must be strictly ordered")
        prior = day
        value = item[symbol]
        if type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError("FRED values must be finite; no silent interpolation")
        rows.append({"date": day.isoformat(), "value": float(value)})
    if not rows:
        raise ValueError("Empty FRED dataset cannot be certified")
    return rows


def freeze_fred_snapshot(symbol: str, start: str, end: str, raw: Any, *,
                         captured_at: object) -> dict:
    """Freeze values with capture-clock provenance, NEVER backdated release."""
    if type(symbol) is not str or not _SYMBOL.fullmatch(symbol):
        raise ValueError("Invalid single FRED series symbol")
    if _day(start) > _day(end):
        raise ValueError("FRED start date exceeds end date")
    stamp = utc_timestamp(captured_at).as_unit("ns")
    if stamp.value < 0 or stamp.value >= 2**63:
        raise ValueError("Invalid capture clock")
    rows = _records(raw, symbol)
    if _day(end) > stamp.date() or any(_day(row["date"]) > stamp.date() for row in rows):
        raise ValueError("Capture cannot predate its requested/observed period")
    if any(not start <= row["date"] <= end for row in rows):
        raise ValueError("FRED provider returned an out-of-range observation")
    frozen = {
        "schema": SCHEMA, "provider": "openbb_fred",
        "provider_target_commit": UPSTREAM_COMMIT,
        "symbol": symbol, "query_start": start, "query_end": end,
        "captured_at_utc": stamp.isoformat(), "rows": rows,
        "historical_release_verified": False,
        "backtest_historical_admissible": False,
        "trade_execution_authorized": False,
    }
    return {**frozen, "snapshot_sha256": _checksum(frozen)}


def verify_fred_snapshot(snapshot: dict) -> dict:
    if type(snapshot) is not dict:
        raise ValueError("Malformed FRED snapshot")
    fields = {"schema", "provider", "provider_target_commit", "symbol",
              "query_start", "query_end", "captured_at_utc", "rows",
              "historical_release_verified", "backtest_historical_admissible",
              "trade_execution_authorized", "snapshot_sha256"}
    if set(snapshot) != fields:
        raise ValueError("FRED snapshot schema drift")
    if snapshot["schema"] != SCHEMA or snapshot["provider"] != "openbb_fred":
        raise ValueError("Unknown FRED snapshot schema")
    if snapshot["provider_target_commit"] != UPSTREAM_COMMIT or any(
        snapshot[k] is not False for k in (
            "historical_release_verified", "backtest_historical_admissible",
            "trade_execution_authorized")
    ):
        raise ValueError("FRED snapshot cannot self-certify historical data")
    rows = snapshot["rows"]
    if type(rows) is not list or not rows:
        raise ValueError("Missing FRED observations")
    raw = [{"date": row["date"], snapshot["symbol"]: row["value"]}
           for row in rows if type(row) is dict and set(row) == {"date", "value"}]
    if len(raw) != len(rows):
        raise ValueError("Malformed FRED observation fields")
    rebuilt = freeze_fred_snapshot(
        snapshot["symbol"], snapshot["query_start"], snapshot["query_end"],
        raw, captured_at=snapshot["captured_at_utc"])
    if snapshot != rebuilt:
        raise ValueError("FRED snapshot digest or content mismatch")
    return rebuilt


def to_prospective_causal_events(snapshot: dict) -> tuple[CausalEvent, ...]:
    """Make all rows known at capture, not at historical observation dates."""
    valid = verify_fred_snapshot(snapshot)
    known_ns = utc_timestamp(valid["captured_at_utc"]).as_unit("ns").value
    return tuple(
        CausalEvent(source="openbb_fred", source_sha256=valid["snapshot_sha256"],
                    kind="economic_observation", event_at_ns=known_ns,
                    available_at_ns=known_ns, sequence=i,
                    values=(row["value"],))
        for i, row in enumerate(valid["rows"])
    )


async def fetch_fred_snapshot(symbol: str, start: str, end: str, *,
                              executor=None, credentials=None, clock=None) -> dict:
    """Call original OpenBB QueryExecutor, read-only FredSeries only.

    Requires optional OpenBB provider dependencies and local FRED API key.
    Fake executor injection supports tests without credentials or network.
    No account, broker or order/trade endpoints.
    """
    if type(symbol) is not str or not _SYMBOL.fullmatch(symbol) or _day(start) > _day(end):
        raise ValueError("Invalid bounded FRED query")
    if executor is None:
        try:
            from openbb_core.provider.query_executor import QueryExecutor
        except ImportError as exc:
            raise RuntimeError("OpenBB provider runtime unavailable") from exc
        executor = QueryExecutor()
    try:
        result = await executor.execute(
            "fred", "FredSeries",
            {"symbol": symbol, "start_date": start, "end_date": end,
             "limit": _MAX_ROWS, "use_cache": False},
            credentials=credentials)
    except Exception:
        raise RuntimeError("FRED read-only query failed") from None
    stamp = (clock or (lambda: pd.Timestamp.now(tz="UTC")))()
    return freeze_fred_snapshot(symbol, start, end, result, captured_at=stamp)
