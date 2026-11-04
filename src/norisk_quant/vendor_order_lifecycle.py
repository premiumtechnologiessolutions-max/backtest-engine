"""Strict vendor-neutral order/event/fill lifecycle audit (synthetic first).

No real vendor process, market data, broker or strategy is run. This proves
internal consistency of CALLER-SUPPLIED order acknowledgements and fills,
not their authenticity or that any exchange or vendor emitted those events.

A complete order lifecycle must go SUBMIT -> ACK -> fills/terminal, or
SUBMIT -> REJECT/CANCEL. No fills before acknowledgements or after terminal
events; no overfills, orphan fills, missing allocations, post-close order
events or incorrectly priced LIMIT fills. No stopped/stop-limit orders yet.
"""
from __future__ import annotations

import hashlib
import json
import math

import pandas as pd

from norisk_quant.campaign_blueprint import verify_blueprint
from norisk_quant.cross_engine_parity import _normalize
from norisk_quant.external_fill_event_reconciliation import (
    _normalize_events, _timestamp, reconcile_vendor_fill_events,
)
from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR

SCHEMA = "NRFX_VENDOR_ORDER_FILL_LIFECYCLE_V1"
_EVENT_FIELDS = frozenset({
    "event_id", "order_id", "trade_id", "at", "sequence",
    "event_type", "action", "phase", "order_quantity",
    "order_type", "limit_price",
})
_ASSIGN_FIELDS = frozenset({"fill_id", "order_id", "sequence"})
_ORDER_TYPES = frozenset({"MARKET", "LIMIT"})
_EVENTS = frozenset({"SUBMIT", "ACK", "CANCEL", "REJECT"})
_MAX = 250_000
_TOL = 1e-7


def _canon(x: object) -> bytes:
    return json.dumps(x, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _hash(x: object) -> str:
    return hashlib.sha256(_canon(x)).hexdigest()


def _id(raw: object, label: str) -> str:
    import re
    if (type(raw) is not str
            or re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", raw) is None):
        raise ValueError(f"Invalid bounded {label} identity")
    return raw


def _sequence(raw: object) -> int:
    if type(raw) is not int or not 0 <= raw < 2**63:
        raise ValueError("Order/fill source sequence must be a bounded integer")
    return raw


def _order_event(event: object) -> dict:
    if type(event) is not dict or set(event) != _EVENT_FIELDS:
        raise ValueError("Vendor order-event schema incomplete")
    order_id = _id(event["order_id"], "order")
    trade_id = _id(event["trade_id"], "trade")
    _id(event["event_id"], "order event")
    action, phase = event["action"], event["phase"]
    event_type = event["event_type"]
    kind = event["order_type"]
    if (type(action) is not str or action not in ("BUY", "SELL")
            or type(phase) is not str or phase not in ("ENTRY", "EXIT")
            or type(event_type) is not str or event_type not in _EVENTS
            or type(kind) is not str or kind not in _ORDER_TYPES):
        raise ValueError("Invalid vendor order lifecycle action/phase/type")
    qty = event["order_quantity"]
    if type(qty) not in (float, int) or not math.isfinite(qty) or qty <= 0:
        raise ValueError("Invalid positive order quantity")
    limit = event["limit_price"]
    if kind == "MARKET":
        if limit is not None:
            raise ValueError("MARKET order cannot claim a LIMIT price")
    elif type(limit) not in (float, int) or not math.isfinite(limit) or limit <= 0:
        raise ValueError("LIMIT order requires a finite positive limit price")
    return {
        "event_id": event["event_id"], "order_id": order_id,
        "trade_id": trade_id, "sequence": _sequence(event["sequence"]),
        "at": _timestamp(event["at"]), "event_type": event_type,
        "action": action, "phase": phase, "order_quantity": float(qty),
        "order_type": kind, "limit_price": None if limit is None else float(limit),
    }


def verify_vendor_order_fill_lifecycles(
    frozen_blueprint: dict,
    normalized_ledgers: dict[str, pd.DataFrame],
    fills_by_engine: dict[str, list[dict]],
    orders_by_engine: dict[str, list[dict]],
    allocations_by_engine: dict[str, list[dict]],
) -> dict:
    """Reconstruct every vendor lifecycle from order events and bound fills.

    The complete underlying per-fill financial reconciliation runs first:
    this helper cannot take order 'success' claims instead of real supplied
    fill rows. Empty ledgers remain UNVERIFIED, even if lifecycle empty.
    """
    plan = verify_blueprint(frozen_blueprint)
    required = set(plan["normalized_spec"]["execution_engines"]) - {"norisk_quant"}
    if (not required or not required <= set(PINNED_VENDOR)
            or type(orders_by_engine) is not dict
            or type(allocations_by_engine) is not dict
            or set(orders_by_engine) != required
            or set(allocations_by_engine) != required):
        raise ValueError("Every frozen vendor needs complete order and fill allocations")
    fill_audit = reconcile_vendor_fill_events(
        plan, normalized_ledgers, fills_by_engine)
    strategies = {s["id"] for s in plan["normalized_spec"]["strategies"]}
    total_orders = total_allocations = 0
    results = {}
    for engine in sorted(required):
        trades, ledger_hash = _normalize(
            engine, normalized_ledgers[engine], strategies)
        order_events = orders_by_engine[engine]
        allocations = allocations_by_engine[engine]
        if (type(order_events) is not list or type(allocations) is not list
                or len(order_events) > _MAX or len(allocations) > _MAX):
            raise ValueError("Bounded vendor order/allocation lists required")
        normalized_fills = _normalize_events(fills_by_engine[engine])
        source_fills = {f["fill_id"]: f for f in normalized_fills}
        if len(allocations) != len(source_fills):
            raise ValueError("Every fill needs exactly one order allocation")
        event_ids, sequence_ids = set(), set()
        timeline = []
        for raw in order_events:
            event = _order_event(raw)
            if (event["event_id"] in event_ids
                    or event["sequence"] in sequence_ids):
                raise ValueError("Duplicate source order event identity or sequence")
            event_ids.add(event["event_id"])
            sequence_ids.add(event["sequence"])
            if event["trade_id"] not in trades:
                raise ValueError("Order points to unknown normalized closed trade")
            trade = trades[event["trade_id"]]
            if not trade["signal_at"] <= event["at"] <= trade["closed_at"]:
                raise ValueError("Order event outside signal/closed-trade chronology")
            timeline.append((event["sequence"], event["at"], "EVENT", event))
        allocated = set()
        mapping = {}
        for raw in allocations:
            if type(raw) is not dict or set(raw) != _ASSIGN_FIELDS:
                raise ValueError("Invalid fill-to-order allocation fields")
            fill_id = _id(raw["fill_id"], "fill")
            order_id = _id(raw["order_id"], "order")
            seq = _sequence(raw["sequence"])
            if (fill_id not in source_fills or fill_id in allocated
                    or seq in sequence_ids):
                raise ValueError("Missing, duplicate or replayed fill allocation")
            allocated.add(fill_id)
            sequence_ids.add(seq)
            mapping[fill_id] = order_id
            fill = source_fills[fill_id]
            timeline.append((seq, fill["at"], "FILL", fill))
        if allocated != set(source_fills):
            raise ValueError("Orphan vendor fill without an allocated order")
        timeline.sort(key=lambda event: event[0])
        orders = {}
        previous_at = None
        for _, at, kind, event in timeline:
            if previous_at is not None and at < previous_at:
                raise ValueError("Out-of-order vendor execution sequence/time")
            previous_at = at
            if kind == "EVENT":
                oid = event["order_id"]
                if event["event_type"] == "SUBMIT":
                    if oid in orders:
                        raise ValueError("Order resubmission or reused order identity")
                    orders[oid] = {
                        "trade_id": event["trade_id"],
                        "action": event["action"], "phase": event["phase"],
                        "quantity": event["order_quantity"],
                        "order_type": event["order_type"],
                        "limit_price": event["limit_price"],
                        "state": "SUBMITTED", "filled": 0.0,
                    }
                    continue
                if oid not in orders:
                    raise ValueError("Acknowledgement/cancellation of unknown order")
                item = orders[oid]
                if (item["trade_id"] != event["trade_id"]
                        or item["action"] != event["action"]
                        or item["phase"] != event["phase"]
                        or item["quantity"] != event["order_quantity"]
                        or item["order_type"] != event["order_type"]
                        or item["limit_price"] != event["limit_price"]):
                    raise ValueError("Order mutable contract drift after submission")
                if event["event_type"] == "ACK":
                    if item["state"] != "SUBMITTED":
                        raise ValueError("Duplicate or late order acknowledgement")
                    item["state"] = "ACKED"
                elif event["event_type"] == "REJECT":
                    if item["state"] != "SUBMITTED":
                        raise ValueError("Rejected order already acknowledged/filled")
                    item["state"] = "REJECTED"
                else:
                    if item["state"] not in ("SUBMITTED", "ACKED"):
                        raise ValueError("Cancellation after terminal order state")
                    item["state"] = "CANCELLED"
            else:
                fill = event
                oid = mapping[fill["fill_id"]]
                if oid not in orders or orders[oid]["state"] != "ACKED":
                    raise ValueError("Fill before acknowledgement or after order terminal")
                item = orders[oid]
                if (item["trade_id"] != fill["trade_id"]
                        or item["phase"] != fill["phase"]
                        or item["action"] != fill["action"]):
                    raise ValueError("Fill allocated to wrong trade or order side")
                limit = item["limit_price"]
                if limit is not None:
                    if item["action"] == "BUY" and fill["price"] > limit + _TOL:
                        raise ValueError("BUY LIMIT fill worse than submitted limit")
                    if item["action"] == "SELL" and fill["price"] < limit - _TOL:
                        raise ValueError("SELL LIMIT fill worse than submitted limit")
                item["filled"] += fill["quantity"]
                if item["filled"] > item["quantity"] + _TOL:
                    raise ValueError("Order quantity overfilled across partial executions")
                if abs(item["filled"] - item["quantity"]) <= _TOL:
                    item["state"] = "FILLED"
        if any(item["state"] in ("SUBMITTED", "ACKED") for item in orders.values()):
            raise ValueError("Incomplete open vendor order lifecycle for closed trade")
        total_orders += len(orders)
        total_allocations += len(allocations)
        results[engine] = {
            "engine": engine,
            "frozen_vendor_commit": PINNED_VENDOR[engine],
            "canonical_trade_ledger_sha256": ledger_hash,
            "order_event_sha256": _hash([x for _, _, k, x in timeline if k == "EVENT"]),
            "fill_allocation_sha256": _hash(
                [{"fill_id": fid, "order_id": oid} for fid, oid in sorted(mapping.items())]),
            "closed_order_count": sum(
                item["state"] == "FILLED" for item in orders.values()),
            "cancelled_order_count": sum(
                item["state"] == "CANCELLED" for item in orders.values()),
            "rejected_order_count": sum(
                item["state"] == "REJECTED" for item in orders.values()),
            "mapped_fill_count": len(allocated),
        }
    payload = {
        "schema": SCHEMA,
        "blueprint_sha256": plan["blueprint_sha256"],
        "fill_reconciliation_sha256": fill_audit["reconciliation_sha256"],
        "vendor_orders": results,
        "total_orders_seen": total_orders,
        "total_mapped_fills": total_allocations,
        "result": ("ZERO_TRADES_NO_VENDOR_ATTESTATION" if
                   fill_audit["total_reconstructed_vendor_trades"] == 0 else
                   "SUPPLIED_ORDER_FILL_LIFECYCLE_CONSISTENT_UNVERIFIED"),
        "vendor_order_source_authenticated": False,
        "vendor_execution_attested": False,
        "broker_or_exchange_fill_verified": False,
        "strategy_research_accepted": False,
        "worker_started": False,
        "market_data_accessed": False,
    }
    return {**payload, "lifecycle_sha256": _hash(payload)}
