"""Strict per-fill reconstruction of normalized external-engine closed trades.

ENGINE CONSTRUCTION ONLY: independently calculate VWAP, exit quantity, USD
gross/net P&L and timestamp boundaries for every supplied LEAN/Nautilus
event. This validates CONSISTENCY of supplied fills and normalized ledgers,
not that the vendor really emitted them or that quotes/broker fills are real.

An external vendor must provide one normalized event stream for every
closed trade in the frozen campaign, including partial fills. No averaging
away mismatches, silent orphan fills, or unsupported position reversals.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

import pandas as pd

from norisk_quant.campaign_blueprint import verify_blueprint
from norisk_quant.cross_engine_parity import _normalize
from norisk_quant.native_export_parity_pipeline import (
    NativeExport, _build_native_export_parity,
)
from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR

SCHEMA = "NRFX_VENDOR_FILL_LEVEL_RECONCILIATION_V1"
_PIPELINE_SCHEMA = "NRFX_VENDOR_FILL_PARITY_PIPELINE_V1"
_EVENT_KEYS = frozenset({
    "fill_id", "trade_id", "at", "action", "phase",
    "quantity", "price", "fee_usd",
})
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,96}\Z")
_MAX_EVENTS = 250_000
_ABS = 1e-7
_FEE_PER_OUNCE = 0.40


def _canon(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _hash(data: object) -> str:
    return hashlib.sha256(_canon(data)).hexdigest()


def _finite(raw: object, field: str, *, positive: bool) -> float:
    if type(raw) not in (int, float):
        raise ValueError(f"Fill {field} must be a real number")
    amount = float(raw)
    if not math.isfinite(amount) or (amount <= 0 if positive else amount < 0):
        raise ValueError(f"Fill {field} is invalid, negative or nonfinite")
    return amount


def _timestamp(raw: object) -> str:
    if type(raw) is not str or len(raw) > 64:
        raise ValueError("Fill timestamp must be a bounded UTC-aware string")
    try:
        at = pd.Timestamp(raw)
        if at.tzinfo is None or pd.isna(at):
            raise ValueError("Unzoned source fill")
        normalized = at.tz_convert("UTC").as_unit("ns")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Invalid fill timestamp") from exc
    return normalized.isoformat()


def _normalize_events(events: list[dict]) -> list[dict]:
    if type(events) is not list or len(events) > _MAX_EVENTS:
        raise ValueError("Unbounded or missing vendor fill events")
    output, fill_ids = [], set()
    previous_at = None
    for event in events:
        if type(event) is not dict or set(event) != _EVENT_KEYS:
            raise ValueError("Incomplete vendor fill event schema")
        event_id, trade_id = event["fill_id"], event["trade_id"]
        if (type(event_id) is not str or not _ID.fullmatch(event_id)
                or event_id in fill_ids
                or type(trade_id) is not str or not _ID.fullmatch(trade_id)
                or event["action"] not in ("BUY", "SELL")
                or event["phase"] not in ("ENTRY", "EXIT")):
            raise ValueError("Duplicate fill identity or invalid order action")
        timestamp = _timestamp(event["at"])
        if previous_at is not None and timestamp < previous_at:
            raise ValueError("Vendor fill source events are out of time order")
        previous_at = timestamp
        fill_ids.add(event_id)
        output.append({
            "fill_id": event_id, "trade_id": trade_id,
            "at": timestamp,
            "action": event["action"], "phase": event["phase"],
            "quantity": _finite(event["quantity"], "quantity", positive=True),
            "price": _finite(event["price"], "price", positive=True),
            "fee_usd": _finite(event["fee_usd"], "fee_usd", positive=False),
        })
    return output


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=0, abs_tol=_ABS)


def _verify_trade(trade: dict, events: list[dict]) -> None:
    if len(events) < 2:
        raise ValueError("Closed trade lacks an entry or exit fill")
    entered, exited = [], []
    in_exit_phase = False
    side = int(trade["side"])
    entry_action = "BUY" if side == 1 else "SELL"
    exit_action = "SELL" if side == 1 else "BUY"
    for event in events:
        if event["phase"] == "EXIT":
            in_exit_phase = True
            if event["action"] != exit_action:
                raise ValueError("Exit order reversed or inconsistent with trade side")
            exited.append(event)
        else:
            if in_exit_phase or event["action"] != entry_action:
                raise ValueError("Entry after exit or wrong-side fill")
            entered.append(event)
    if not entered or not exited:
        raise ValueError("Closed trade lacks both entry and exit events")
    qty_entry = math.fsum(e["quantity"] for e in entered)
    qty_exit = math.fsum(e["quantity"] for e in exited)
    if not (_close(qty_entry, qty_exit)
            and _close(qty_entry, trade["ounces"])):
        raise ValueError("Unbalanced or missing partial fill quantities")
    if (entered[0]["at"] != trade["entry_at"]
            or exited[-1]["at"] != trade["closed_at"]
            or entered[-1]["at"] > exited[0]["at"]):
        raise ValueError("Fill chronology differs from normalized trade")
    if entered[0]["at"] < trade["signal_at"]:
        raise ValueError("Fill occurred before signal knowledge timestamp")
    entry_vwap = math.fsum(e["quantity"] * e["price"] for e in entered) / qty_entry
    exit_vwap = math.fsum(e["quantity"] * e["price"] for e in exited) / qty_exit
    costs = math.fsum(e["fee_usd"] for e in events)
    gross = side * math.fsum(
        [exit_vwap * qty_exit, -entry_vwap * qty_entry])
    if (not _close(entry_vwap, trade["entry_price"])
            or not _close(exit_vwap, trade["exit_price"])
            or not _close(costs, _FEE_PER_OUNCE * trade["ounces"])
            or not _close(costs, trade["cost"])
            or not _close(gross, trade["gross_pnl"])
            or not _close(gross - costs, trade["net_pnl"])):
        raise ValueError("Independent fill VWAP, gross/net P&L or fees disagree")
    reason = trade["exit_reason"]
    if reason in ("stop", "ambiguous_stop_first"):
        if not _close(exit_vwap, trade["stop"]):
            raise ValueError("Stop fill price is inconsistent with declared exit")
    elif reason in ("target", "open_target"):
        if not _close(exit_vwap, trade["target"]):
            raise ValueError("Target fill price is inconsistent with declared exit")
    elif reason in ("open_stop", "gap_stop", "entry_open_beyond_stop"):
        if side * (exit_vwap - trade["stop"]) > _ABS:
            raise ValueError("Adverse stop fill falsely improved past stop")
    elif reason not in ("end_of_data", "time_exit"):
        raise ValueError("Unsupported fill-level exit classification")


def reconcile_vendor_fill_events(
    frozen_blueprint: dict, ledgers: dict[str, pd.DataFrame],
    fills_by_engine: dict[str, list[dict]],
) -> dict:
    """Require ALL planned external engines with all their individual fills.

    The first-party NRFX simulator only has minute OHLC trades, not real
    broker order events; no false assertion is made that it has fill proof.
    """
    plan = verify_blueprint(frozen_blueprint)
    required = set(plan["normalized_spec"]["execution_engines"]) - {"norisk_quant"}
    if (not required or not required <= set(PINNED_VENDOR)
            or type(ledgers) is not dict
            or set(ledgers) != set(plan["normalized_spec"]["execution_engines"])
            or type(fills_by_engine) is not dict
            or set(fills_by_engine) != required):
        raise ValueError("Every planned external engine requires its full fill stream")
    strategies = {s["id"] for s in plan["normalized_spec"]["strategies"]}
    results, total_fills, total_trades = {}, 0, 0
    for engine in sorted(required):
        trades, ledger_sha = _normalize(engine, ledgers[engine], strategies)
        normalized = _normalize_events(fills_by_engine[engine])
        grouped = {trade_id: [] for trade_id in trades}
        for event in normalized:
            trade_id = event["trade_id"]
            if trade_id not in grouped:
                raise ValueError("Orphan or fabricated source fill trade ID")
            grouped[trade_id].append(event)
        # Empty trade ledger is not proof the vendor was started.
        for trade_id in sorted(trades):
            _verify_trade(trades[trade_id], grouped[trade_id])
        total_fills += len(normalized)
        total_trades += len(trades)
        results[engine] = {
            "engine": engine,
            "frozen_upstream_commit": PINNED_VENDOR[engine],
            "canonical_ledger_sha256": ledger_sha,
            "fill_stream_sha256": _hash(normalized),
            "reconstructed_trade_count": len(trades),
            "validated_fill_events": len(normalized),
        }
    payload = {
        "schema": SCHEMA,
        "frozen_blueprint_sha256": plan["blueprint_sha256"],
        "per_vendor": results,
        "total_vendor_fill_events": total_fills,
        "total_reconstructed_vendor_trades": total_trades,
        "status": (
            "ZERO_TRADES_UNVERIFIED" if total_trades == 0
            else "SUPPLIED_FILL_LEDGER_CONSISTENCY_UNVERIFIED"
        ),
        "fixed_total_fee_usd_per_ounce": _FEE_PER_OUNCE,
        "all_vendor_events_supplied_for_each_ledger_trade": True,
        "vendor_process_execution_attested": False,
        "vendor_fill_origin_authenticated": False,
        "quote_or_broker_fill_reality_verified": False,
        "independent_oos_proven": False,
        "strategy_research_accepted": False,
        "market_data_opened": False,
        "worker_started": False,
    }
    return {**payload, "reconciliation_sha256": _hash(payload)}


def normalize_compare_and_reconcile_vendor_fills(
    frozen_blueprint: dict,
    nrfx_ledger: pd.DataFrame,
    native_vendor_exports: dict[str, NativeExport],
    fills_by_engine: dict[str, list[dict]],
) -> dict:
    """One functional conversion + row-parity + per-fill reconciliation API."""
    comparison, ledgers = _build_native_export_parity(
        frozen_blueprint, nrfx_ledger, native_vendor_exports)
    fill_audit = reconcile_vendor_fill_events(
        frozen_blueprint, ledgers, fills_by_engine)
    payload = {
        "schema": _PIPELINE_SCHEMA,
        "native_export_parity": comparison,
        "vendor_fill_event_audit": fill_audit,
        "result": "SOURCE_SHAPED_EVENT_AND_LEDGER_MATCH_UNVERIFIED",
        "vendor_execution_attested": False,
        "research_result_accepted": False,
        "original_gold_archive_opened": False,
    }
    return {**payload, "pipeline_sha256": _hash(payload)}
