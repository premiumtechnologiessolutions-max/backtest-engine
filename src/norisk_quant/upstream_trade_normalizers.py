"""Strict, SOURCE-SHAPED trade normalizers for pinned LEAN / NautilusTrader.

These are functional pure-data converters, not executors. They support only
simple, closed, one-instrument, USD-linear one-ounce-per-unit trades with
unambiguous externally supplied signal sidecars. Reject unknown quantity
multipliers, mixed currencies, snapshots, partials and missing fields.
An owner-supplied sidecar/hash does NOT authenticate its pre-execution origin.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import re

import pandas as pd

from norisk_quant.cross_engine_parity import _FIELDS, _normalize

SCHEMA = "NRFX_UPSTREAM_TRADE_NORMALIZER_V1"
PINNED_VENDOR = {
    "lean": "9ecfed98339c27849a2a708edc03455caf151e91",
    "nautilus": "6c843bc7f9f72941eeddb22df502b520c97a8987",
}
_SIDECAR_KEYS = frozenset({
    "trade_id", "strategy", "signal_at", "stop", "target",
    "exit_reason", "gap_minutes",
})
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_ROWS = 100_000


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _number(value: object, label: str) -> float:
    if type(value) not in (int, float, str, Decimal):
        raise ValueError(f"Unsupported upstream {label} numeric type")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid upstream {label} amount") from exc
    if not number.is_finite():
        raise ValueError(f"Nonfinite upstream {label} amount")
    converted = float(number)
    if not math.isfinite(converted):
        raise ValueError(f"Unbounded upstream {label} amount")
    return converted


def _money(value: object, label: str) -> float:
    if type(value) is not str:
        raise ValueError(f"Upstream {label} requires explicit USD denomination")
    raw = value.split(" ")
    if len(raw) != 2 or raw[1] != "USD":
        raise ValueError(f"Unsupported upstream {label} currency")
    return _number(raw[0], label)


def _common(raw_id: str, spec: dict, entry_at: object, closed_at: object,
            side: int, entry_price: float, exit_price: float, ounces: float,
            gross_pnl: float, cost: float) -> dict:
    if type(spec) is not dict or set(spec) != _SIDECAR_KEYS:
        raise ValueError("Frozen source mapping is incomplete or includes execution overrides")
    if (type(spec["trade_id"]) is not str or
            not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", spec["trade_id"])
            or type(spec["strategy"]) is not str
            or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", spec["strategy"])
            or type(spec["exit_reason"]) is not str):
        raise ValueError("Bad normalized strategy/correlation identity")
    if type(spec["gap_minutes"]) is not int or spec["gap_minutes"] < 0:
        raise ValueError("Invalid immutable gap count")
    # Never allow the sidecar to change provider entry, exit, fee or quantity.
    row = {
        "trade_id": spec["trade_id"], "strategy": spec["strategy"],
        "signal_at": spec["signal_at"], "entry_at": entry_at,
        "closed_at": closed_at, "side": side,
        "entry_price": entry_price, "exit_price": exit_price,
        "stop": _number(spec["stop"], "stop"),
        "target": _number(spec["target"], "target"),
        "ounces": ounces, "gross_pnl": gross_pnl, "cost": cost,
        "net_pnl": gross_pnl - cost,
        "exit_reason": spec["exit_reason"],
        "gap_minutes": spec["gap_minutes"],
    }
    return row


def _sidecars(raw_ids: list[str], sidecars: dict, expected_sha: str) -> None:
    if type(sidecars) is not dict or type(expected_sha) is not str or not _SHA.fullmatch(expected_sha):
        raise ValueError("Exact immutable sidecar hash required")
    if (set(raw_ids) != set(sidecars)
            or len(raw_ids) != len(set(raw_ids))
            or any(type(k) is not str or not _ID.fullmatch(k) for k in raw_ids)):
        raise ValueError("Source rows and frozen sidecars disagree or duplicate")
    try:
        digest = hashlib.sha256(_canonical(sidecars)).hexdigest()
    except (TypeError, ValueError) as exc:
        raise ValueError("Noncanonical upstream sidecar") from exc
    if digest != expected_sha:
        raise ValueError("Frozen upstream sidecar hash mismatch")


def _finish(provider: str, rows: list[dict], raw_source_count: int) -> tuple[pd.DataFrame, dict]:
    frame = pd.DataFrame(rows, columns=_FIELDS)
    strategies = {item["strategy"] for item in rows}
    normalized, digest = _normalize(provider, frame, strategies)
    return frame, {
        "schema": SCHEMA,
        "provider": provider,
        "pinned_upstream_commit": PINNED_VENDOR[provider],
        "source_rows": raw_source_count,
        "normalized_trade_count": len(normalized),
        "normalized_ledger_sha256": digest,
        "status": "NORMALIZED_NOT_ENGINE_ATTESTED",
        "vendor_runtime_was_started_here": False,
        "provider_execution_attested": False,
        "sidecar_was_frozen_before_execution_proven": False,
        "original_quote_bytes_verified": False,
        "fills_and_order_events_reconciled": False,
        "cross_engine_result_accepted": False,
    }


def normalize_lean_closed_trades(
    source_rows: list[dict], sidecars: dict, *,
    expected_sidecar_sha256: str, source_symbol: str,
    vendor_commit: str,
) -> tuple[pd.DataFrame, dict]:
    """Adapt documented LEAN ClosedTrade fields, NOT arbitrary orders.

    LEAN's native closed-trade IDs cannot be assumed equal to strategy
    signal IDs. The exact sidecar must provide that mapping. Aggregated
    closed trades do not prove partial-fill/stop history; the adapter
    rejects apparent non-USD/oz accounting instead of recalculating it.
    """
    if vendor_commit != PINNED_VENDOR["lean"]:
        raise ValueError("Unsupported LEAN source version")
    if type(source_symbol) is not str or not _ID.fullmatch(source_symbol):
        raise ValueError("Frozen LEAN symbol required")
    if type(source_rows) is not list or len(source_rows) > _MAX_ROWS:
        raise ValueError("Bounded LEAN closed-trade JSON array required")
    needed = {
        "id", "entryTime", "exitTime", "direction", "quantity",
        "entryPrice", "exitPrice", "profitLoss", "totalFees", "symbols",
    }
    if any(type(row) is not dict or not needed <= set(row) for row in source_rows):
        raise ValueError("LEAN closed trades lack required upstream fields")
    identifiers = [row["id"] for row in source_rows]
    _sidecars(identifiers, sidecars, expected_sidecar_sha256)
    rows = []
    for item in source_rows:
        if (type(item["symbols"]) is not list or
                item["symbols"] != [source_symbol]):
            raise ValueError("LEAN closed trade must have exact one frozen USD-linear symbol")
        if type(item["direction"]) is not int or item["direction"] not in (0, 1):
            raise ValueError("Unsupported LEAN direction")
        side = 1 if item["direction"] == 0 else -1
        ounces = _number(item["quantity"], "quantity")
        entry = _number(item["entryPrice"], "entry_price")
        exit = _number(item["exitPrice"], "exit_price")
        gross = _number(item["profitLoss"], "profit_loss")
        fee = _number(item["totalFees"], "total_fees")
        expected_gross = side * (exit - entry) * ounces
        if (not math.isclose(gross, expected_gross, abs_tol=1e-7, rel_tol=0)
                or not math.isclose(fee, 0.4 * ounces, abs_tol=1e-7, rel_tol=0)):
            raise ValueError("LEAN gross/fee not compatible with frozen USD-per-oz contract")
        rows.append(_common(
            item["id"], sidecars[item["id"]],
            item["entryTime"], item["exitTime"], side, entry, exit,
            ounces, gross, fee))
    return _finish("lean", rows, len(source_rows))


def normalize_nautilus_positions_report(
    positions: pd.DataFrame, sidecars: dict, *,
    expected_sidecar_sha256: str, instrument_id: str,
    vendor_commit: str,
) -> tuple[pd.DataFrame, dict]:
    """Adapt documented NautilusTrader closed simple positions only.

    Native position snapshots, reopenings, NETTING cycles, mixed-currency
    commissions and multipliers other than USD-linear one ounce per unit
    require a fill-level adapter instead. No guesswork or aggregation.
    """
    if vendor_commit != PINNED_VENDOR["nautilus"]:
        raise ValueError("Unsupported NautilusTrader source version")
    if type(instrument_id) is not str or not _ID.fullmatch(instrument_id):
        raise ValueError("Frozen Nautilus instrument ID required")
    needed = {
        "instrument_id", "strategy_id", "entry", "side", "quantity",
        "peak_qty", "avg_px_open", "avg_px_close",
        "commissions", "realized_pnl", "ts_opened", "ts_closed", "is_snapshot",
    }
    if (not isinstance(positions, pd.DataFrame)
            or positions.index.name != "position_id"
            or positions.index.has_duplicates
            or positions.columns.has_duplicates
            or not needed <= set(positions.columns)
            or len(positions) > _MAX_ROWS):
        raise ValueError("Nautilus closed position report schema/IDs invalid")
    identifiers = positions.index.tolist()
    _sidecars(identifiers, sidecars, expected_sidecar_sha256)
    rows = []
    for pos_id, item in positions.iterrows():
        if (item["is_snapshot"] is not False
                or item["instrument_id"] != instrument_id
                or item["strategy_id"] != sidecars[pos_id]["strategy"]
                or item["side"] != "FLAT"
                or item["entry"] not in ("BUY", "SELL")):
            raise ValueError("Unsupported Nautilus snapshot/position lifecycle or symbol")
        if _number(item["quantity"], "flat_quantity") != 0:
            raise ValueError("Nautilus position is not fully closed")
        ounces = _number(item["peak_qty"], "peak_qty")
        entry = _number(item["avg_px_open"], "avg_px_open")
        exit = _number(item["avg_px_close"], "avg_px_close")
        side = 1 if item["entry"] == "BUY" else -1
        commission = item["commissions"]
        if type(commission) is not list or len(commission) != 1:
            raise ValueError("One explicit USD commission total required")
        fee = _money(commission[0], "commission")
        net = _money(item["realized_pnl"], "realized_pnl")
        gross = side * (exit - entry) * ounces
        if (not math.isclose(fee, 0.4 * ounces, abs_tol=1e-7, rel_tol=0)
                or not math.isclose(net, gross - fee, abs_tol=1e-7, rel_tol=0)):
            raise ValueError("Nautilus realized USD P/L or fee not compatible with frozen accounting")
        rows.append(_common(
            pos_id, sidecars[pos_id], item["ts_opened"], item["ts_closed"],
            side, entry, exit, ounces, gross, fee))
    return _finish("nautilus", rows, len(positions))
