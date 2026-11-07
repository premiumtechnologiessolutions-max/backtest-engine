"""Independent, fail-closed cross-engine trade-ledger comparison.

Compares *normalized* reference-engine trade rows at full row granularity.
This module does NOT import, start, authenticate or run LEAN/Nautilus/NRFX.
All results remain UNVERIFIED; equality alone cannot establish correct fills,
data provenance, intrabar ordering, execution parity or profitable edge.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

import numpy as np
import pandas as pd

from norisk_quant.campaign_blueprint import verify_blueprint

SCHEMA = "NRFX_CROSS_ENGINE_LEDGER_PARITY_V1"
_FIELDS = (
    "trade_id", "strategy", "signal_at", "entry_at", "closed_at",
    "side", "entry_price", "exit_price", "stop", "target", "ounces",
    "gross_pnl", "cost", "net_pnl", "exit_reason", "gap_minutes",
)
_TIME = {"signal_at", "entry_at", "closed_at"}
_INTEGER = {"side", "gap_minutes"}
_TEXT = {"trade_id", "strategy", "exit_reason"}
_NUMERIC = tuple(x for x in _FIELDS if x not in _TIME | _INTEGER | _TEXT)
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,96}\Z")
_EXIT = frozenset({
    "stop", "ambiguous_stop_first", "target", "open_target",
    "open_stop", "gap_stop", "entry_open_beyond_stop",
    "end_of_data", "time_exit",
})
_MAX_TRADES_PER_ENGINE = 250_000
_ABS = 1e-7


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _normalize(name: str, frame: pd.DataFrame, strategies: set[str]) -> tuple[dict, str]:
    if (not isinstance(frame, pd.DataFrame)
            or frame.columns.has_duplicates or set(frame.columns) != set(_FIELDS)
            or len(frame) > _MAX_TRADES_PER_ENGINE):
        raise ValueError(f"{name}: missing, duplicate or unbounded canonical trade columns")
    if frame.empty:
        return {}, hashlib.sha256(_canonical([])).hexdigest()
    for col in _NUMERIC:
        dtype = frame[col].dtype
        if (not pd.api.types.is_numeric_dtype(dtype)
                or pd.api.types.is_bool_dtype(dtype)
                or pd.api.types.is_complex_dtype(dtype)):
            raise ValueError(f"{name}: non-real numeric trade field {col}")
    for col in _INTEGER:
        dtype = frame[col].dtype
        if (not pd.api.types.is_integer_dtype(dtype)
                or pd.api.types.is_bool_dtype(dtype)):
            raise ValueError(f"{name}: invalid integer trade field {col}")
    records = {}
    for item in frame.to_dict(orient="records"):
        trade_id, strategy = item["trade_id"], item["strategy"]
        if (type(trade_id) is not str or not _ID.fullmatch(trade_id)
                or trade_id in records
                or type(strategy) is not str or strategy not in strategies
                or type(item["exit_reason"]) is not str
                or item["exit_reason"] not in _EXIT):
            raise ValueError(f"{name}: duplicate or unregistered normalized trade identity")
        item["side"] = int(item["side"])
        item["gap_minutes"] = int(item["gap_minutes"])
        if item["side"] not in (-1, 1) or item["gap_minutes"] < 0:
            raise ValueError(f"{name}: bad trade side or missing minutes")
        for col in _NUMERIC:
            amount = float(item[col])
            if not math.isfinite(amount):
                raise ValueError(f"{name}: nonfinite trade amount")
            item[col] = amount
        if (item["ounces"] <= 0
                or min(item[k] for k in (
                    "entry_price", "exit_price", "stop", "target")) <= 0
                or item["cost"] < 0):
            raise ValueError(f"{name}: negative quantity, cost or price")
        if item["side"] == 1:
            valid_levels = item["stop"] < item["entry_price"] < item["target"]
        else:
            valid_levels = item["target"] < item["entry_price"] < item["stop"]
        if not valid_levels:
            raise ValueError(f"{name}: invalid protective price geometry")
        gross = item["side"] * (item["exit_price"] - item["entry_price"]) * item["ounces"]
        fee = 0.40 * item["ounces"]
        if (not math.isclose(item["gross_pnl"], gross, rel_tol=0, abs_tol=_ABS)
                or not math.isclose(item["cost"], fee, rel_tol=0, abs_tol=_ABS)
                or not math.isclose(item["net_pnl"], gross - fee,
                                     rel_tol=0, abs_tol=_ABS)):
            raise ValueError(f"{name}: independent USD/oz trade accounting mismatch")
        for col in _TIME:
            raw = item[col]
            if isinstance(raw, bool) or not isinstance(raw, (str, pd.Timestamp)):
                raise ValueError(f"{name}: invalid UTC trade timestamp")
            try:
                stamp = pd.Timestamp(raw)
                if stamp.tzinfo is None or pd.isna(stamp):
                    raise ValueError("Timezone-naive trade")
                # Exact nanosecond UTC for consistent cross-engine comparison.
                utc = stamp.tz_convert("UTC").as_unit("ns")
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError(f"{name}: invalid UTC trade timestamp") from exc
            item[col] = utc.isoformat()
        if not (item["signal_at"] <= item["entry_at"] <= item["closed_at"]):
            raise ValueError(f"{name}: future-leaking or reversed trade chronology")
        records[trade_id] = item
    digest = hashlib.sha256(_canonical(
        [records[key] for key in sorted(records)])).hexdigest()
    return records, digest


def compare_frozen_engine_ledgers(
    blueprint: dict, ledgers: dict[str, pd.DataFrame], *,
    tolerance: float = 1e-7, max_differences: int = 100,
) -> dict:
    """Compare every frozen reference engine; never cherry-pick comparators.

    The common trade_id is assigned by future engine-specific normalization.
    This helper verifies neither the ID's source nor provider execution.
    Each strategy in the frozen blueprint is an allowed trade strategy, but
    absence of trades cannot prove the engine ran the strategy.
    """
    frozen = verify_blueprint(blueprint)
    expected = frozen["normalized_spec"]["execution_engines"]
    if (len(expected) < 2 or type(ledgers) is not dict
            or set(ledgers) != set(expected)
            or type(max_differences) is not int
            or not 1 <= max_differences <= 1000
            or type(tolerance) not in (int, float)
            or not math.isfinite(tolerance)
            or not 0 <= tolerance <= 0.01):
        raise ValueError("All frozen engines, bounded diagnostic options required")
    strategies = {s["id"] for s in frozen["normalized_spec"]["strategies"]}
    normalized = {}
    hashes = {}
    for engine in sorted(expected):
        rows, sha = _normalize(engine, ledgers[engine], strategies)
        normalized[engine], hashes[engine] = rows, sha
    reference = normalized["norisk_quant"]
    differences = []
    total = 0
    matched = {}
    for engine in sorted(set(expected) - {"norisk_quant"}):
        comparator = normalized[engine]
        good = 0
        for trade_id in sorted(set(reference) | set(comparator)):
            if trade_id not in reference or trade_id not in comparator:
                total += 1
                if len(differences) < max_differences:
                    differences.append({
                        "engine": engine, "trade_id": trade_id,
                        "field": "presence",
                        "reason": ("MISSING_REFERENCE" if trade_id not in reference
                                   else "MISSING_COMPARATOR"),
                    })
                continue
            fields_match = True
            for field in _FIELDS[1:]:
                a, b = reference[trade_id][field], comparator[trade_id][field]
                equal = (abs(a - b) <= tolerance if field in _NUMERIC
                         else a == b)
                if not equal:
                    fields_match = False
                    total += 1
                    if len(differences) < max_differences:
                        differences.append({
                            "engine": engine, "trade_id": trade_id,
                            "field": field, "reason": "FIELD_MISMATCH",
                            # Do NOT export private strategy prices into logs.
                        })
            if fields_match:
                good += 1
        matched[engine] = good
    count = len(reference)
    no_trades = all(not rows for rows in normalized.values())
    status = (
        "NO_TRADES_UNVERIFIED" if no_trades else
        "ROW_PARITY_MATCH_UNVERIFIED" if total == 0 else
        "ROW_PARITY_DISAGREEMENT_UNVERIFIED"
    )
    payload = {
        "schema": SCHEMA,
        "blueprint_sha256": frozen["blueprint_sha256"],
        "comparison_engines": sorted(expected),
        "normalized_ledger_sha256": hashes,
        "reference_trade_count": count,
        "per_engine_trade_count": {
            engine: len(rows) for engine, rows in normalized.items()},
        "fully_matching_reference_trades": matched,
        "field_discrepancy_count": total,
        "discrepancies_truncated": total > len(differences),
        "discrepancies": differences,
        "status": status,
        "fixed_all_in_fee_usd_per_ounce": 0.40,
        "upstream_engine_execution_attested": False,
        "quote_source_provenance_verified": False,
        "independent_fill_accuracy_proven": False,
        "strategy_research_accepted": False,
        "market_data_opened": False,
        "worker_started": False,
        "live_trading_authorized": False,
    }
    return {**payload, "diagnostic_sha256":
            hashlib.sha256(_canonical(payload)).hexdigest()}
