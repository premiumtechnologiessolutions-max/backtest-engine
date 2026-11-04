"""Synthetic order lifecycle math and adverse conditions; never runs trading."""
import copy

import pandas as pd
import pytest

from norisk_quant.campaign_blueprint import freeze_blueprint
from norisk_quant.vendor_order_lifecycle import verify_vendor_order_fill_lifecycles


def frozen():
    return freeze_blueprint({
        "source_commit": "a" * 40,
        "dataset": {"id": "xauusd_m1", "archive_sha256": "b" * 64,
                    "start": "2026-01-01", "end": "2026-01-31",
                    "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2026-01-01", "end": "2026-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [{"id": "sweep", "code_sha256": "c" * 64,
                        "spec_sha256": "d" * 64}],
        "execution_engines": ["norisk_quant", "lean", "nautilus"],
        "ai_reviewers": [], "resource_limits": {
            "max_workers": 1, "max_ram_mb": 2048,
            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": .4,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    })


def ledger():
    return pd.DataFrame([{
        "trade_id": "T1", "strategy": "sweep",
        "signal_at": "2026-01-02T10:00:00Z",
        "entry_at": "2026-01-02T10:01:00Z",
        "closed_at": "2026-01-02T10:05:00Z",
        "side": 1, "entry_price": 2000., "exit_price": 2003.,
        "stop": 1995., "target": 2006., "ounces": 1.,
        "gross_pnl": 3., "cost": .4, "net_pnl": 2.6,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }])


def fills():
    return [
        dict(fill_id="F1", trade_id="T1",
             at="2026-01-02T10:01:00Z", action="BUY", phase="ENTRY",
             quantity=.4, price=2000., fee_usd=.08),
        dict(fill_id="F2", trade_id="T1",
             at="2026-01-02T10:02:00Z", action="BUY", phase="ENTRY",
             quantity=.6, price=2000., fee_usd=.12),
        dict(fill_id="F3", trade_id="T1",
             at="2026-01-02T10:05:00Z", action="SELL", phase="EXIT",
             quantity=1., price=2003., fee_usd=.2),
    ]


def order(order_id, sequence, event_type, time, phase, action,
          quantity=1., kind="MARKET", limit=None):
    return dict(event_id=f"{order_id}-{sequence}", order_id=order_id,
                trade_id="T1", sequence=sequence, at=time,
                event_type=event_type, action=action, phase=phase,
                order_quantity=quantity, order_type=kind, limit_price=limit)


def order_events():
    return [
        order("ENTRY1", 1, "SUBMIT", "2026-01-02T10:00:00Z", "ENTRY", "BUY"),
        order("ENTRY1", 2, "ACK", "2026-01-02T10:00:00Z", "ENTRY", "BUY"),
        order("EXIT1", 5, "SUBMIT", "2026-01-02T10:04:00Z", "EXIT", "SELL"),
        order("EXIT1", 6, "ACK", "2026-01-02T10:04:00Z", "EXIT", "SELL"),
    ]


def allocations():
    return [
        {"fill_id": "F1", "order_id": "ENTRY1", "sequence": 3},
        {"fill_id": "F2", "order_id": "ENTRY1", "sequence": 4},
        {"fill_id": "F3", "order_id": "EXIT1", "sequence": 7},
    ]


def run(order_stream=None, fill_stream=None, allocation=None):
    orders = order_events() if order_stream is None else order_stream
    fs = fills() if fill_stream is None else fill_stream
    alloc = allocations() if allocation is None else allocation
    return verify_vendor_order_fill_lifecycles(
        frozen(), {k: ledger() for k in ("norisk_quant", "lean", "nautilus")},
        {"lean": copy.deepcopy(fs), "nautilus": fills()},
        {"lean": copy.deepcopy(orders), "nautilus": order_events()},
        {"lean": copy.deepcopy(alloc), "nautilus": allocations()},
    )


def test_partial_fill_allocation_has_full_lifecycle_proof_but_no_market_attestation():
    result = run()
    assert result["total_orders_seen"] == 4
    assert result["total_mapped_fills"] == 6
    assert result["vendor_order_source_authenticated"] is False
    assert result["vendor_execution_attested"] is False
    assert result["strategy_research_accepted"] is False


def test_repeated_input_reproduces_same_attestation_hash():
    assert run() == run()


def test_unacknowledged_fill_refused():
    orders = order_events()
    orders.pop(1)
    with pytest.raises(ValueError, match="before acknowledgement"):
        run(order_stream=orders)


def test_extra_fill_without_order_allocation_refused():
    alloc = allocations()[:-1]
    with pytest.raises(ValueError, match="exactly one"):
        run(allocation=alloc)


def test_partial_overfill_refused_even_if_close_trade_accounting_matches():
    orders = order_events()
    orders[0]["order_quantity"] = 0.5
    orders[1]["order_quantity"] = 0.5
    with pytest.raises(ValueError, match="overfilled"):
        run(order_stream=orders)


def test_order_may_not_be_cancelled_then_filled():
    orders = order_events()
    orders.insert(2, order("ENTRY1", 3, "CANCEL",
                           "2026-01-02T10:00:00Z", "ENTRY", "BUY"))
    orders[3]["sequence"] = 6
    orders[4]["sequence"] = 7
    allocation = allocations()
    allocation[0]["sequence"] = 4
    allocation[1]["sequence"] = 5
    allocation[2]["sequence"] = 8
    with pytest.raises(ValueError, match="before acknowledgement or after order terminal"):
        run(order_stream=orders, allocation=allocation)


def test_duplicate_ack_refused():
    orders = order_events()
    orders.insert(2, order("ENTRY1", 20, "ACK",
                           "2026-01-02T10:05:00Z", "ENTRY", "BUY"))
    with pytest.raises(ValueError, match="Duplicate or late"):
        run(order_stream=orders)


def test_mutating_submitted_order_terms_refused():
    orders = order_events()
    orders[1]["order_quantity"] = 2.
    with pytest.raises(ValueError, match="mutable contract"):
        run(order_stream=orders)


def test_wrong_order_side_and_orphan_refused():
    allocation = allocations()
    allocation[2]["order_id"] = "ENTRY1"
    with pytest.raises(ValueError, match="wrong trade or order side"):
        run(allocation=allocation)
    allocation = allocations()
    allocation[2]["order_id"] = "NOT_SUBMITTED"
    with pytest.raises(ValueError, match="before acknowledgement"):
        run(allocation=allocation)


def test_limit_buy_must_not_fill_above_limit():
    orders = order_events()
    orders[0]["order_type"] = "LIMIT"
    orders[0]["limit_price"] = 1999.
    orders[1]["order_type"] = "LIMIT"
    orders[1]["limit_price"] = 1999.
    with pytest.raises(ValueError, match="BUY LIMIT"):
        run(order_stream=orders)


def test_unbounded_future_or_time_reversal_refused():
    orders = order_events()
    orders[0]["at"] = "2026-01-03T10:00:00Z"
    with pytest.raises(ValueError, match="outside signal"):
        run(order_stream=orders)


def test_boolean_sequence_or_quantity_refused():
    orders = order_events()
    orders[0]["sequence"] = True
    with pytest.raises(ValueError, match="sequence"):
        run(order_stream=orders)
    orders = order_events()
    orders[0]["order_quantity"] = True
    with pytest.raises(ValueError, match="quantity"):
        run(order_stream=orders)


def test_missing_vendor_engine_stream_refused():
    with pytest.raises(ValueError, match="Every frozen vendor"):
        verify_vendor_order_fill_lifecycles(
            frozen(), {k: ledger() for k in ("norisk_quant", "lean", "nautilus")},
            {"lean": fills(), "nautilus": fills()},
            {"lean": order_events()}, {"lean": allocations(), "nautilus": allocations()})


def test_order_state_must_be_terminal_even_when_no_fills_for_that_order():
    orders = order_events()
    orders.append(order("UNUSED", 8, "SUBMIT", "2026-01-02T10:05:00Z",
                        "EXIT", "SELL", quantity=.5))
    with pytest.raises(ValueError, match="Incomplete open"):
        run(order_stream=orders)
