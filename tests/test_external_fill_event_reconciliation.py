"""Synthetic multi-fill reconstruction, never real vendor execution."""
import copy
import hashlib
import json

import pandas as pd
import pytest

from norisk_quant.campaign_blueprint import freeze_blueprint
from norisk_quant.external_fill_event_reconciliation import (
    reconcile_vendor_fill_events, normalize_compare_and_reconcile_vendor_fills,
)
from norisk_quant.native_export_parity_pipeline import NativeExport
from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR


def blueprint():
    return freeze_blueprint({
        "source_commit": "a" * 40,
        "dataset": {"id": "xauusd_m1", "archive_sha256": "b" * 64,
                    "start": "2026-01-01", "end": "2026-01-31",
                    "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2026-01-01", "end": "2026-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [{"id": "sweep_fib", "code_sha256": "c" * 64,
                        "spec_sha256": "d" * 64}],
        "execution_engines": ["norisk_quant", "lean", "nautilus"],
        "ai_reviewers": [],
        "resource_limits": {"max_workers": 1, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.4,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    })


def ledger():
    entry = 0.4 * 2000.0 + 0.6 * 2002.0
    exit_ = 0.25 * 2003.0 + 0.75 * 2005.0
    pnl = exit_ - entry
    return pd.DataFrame([{
        "trade_id": "sweep_001", "strategy": "sweep_fib",
        "signal_at": "2026-01-05T10:00:00Z",
        "entry_at": "2026-01-05T10:01:00Z",
        "closed_at": "2026-01-05T10:07:00Z",
        "side": 1, "entry_price": entry, "exit_price": exit_,
        "stop": 1995.0, "target": 2008.0,
        "ounces": 1.0, "gross_pnl": pnl, "cost": 0.4,
        "net_pnl": pnl - 0.4, "exit_reason": "time_exit",
        "gap_minutes": 0,
    }])


def events():
    return [
        dict(fill_id="E001", trade_id="sweep_001",
             at="2026-01-05T10:01:00Z", action="BUY", phase="ENTRY",
             quantity=0.4, price=2000.0, fee_usd=0.08),
        dict(fill_id="E002", trade_id="sweep_001",
             at="2026-01-05T10:02:00Z", action="BUY", phase="ENTRY",
             quantity=0.6, price=2002.0, fee_usd=0.12),
        dict(fill_id="X001", trade_id="sweep_001",
             at="2026-01-05T10:05:00Z", action="SELL", phase="EXIT",
             quantity=0.25, price=2003.0, fee_usd=0.05),
        dict(fill_id="X002", trade_id="sweep_001",
             at="2026-01-05T10:07:00Z", action="SELL", phase="EXIT",
             quantity=0.75, price=2005.0, fee_usd=0.15),
    ]


def ledgers():
    return {"norisk_quant": ledger().copy(),
            "lean": ledger().copy(), "nautilus": ledger().copy()}


def sources():
    return {"lean": events(), "nautilus": events()}


def test_partial_fills_reconstruct_weighted_entries_exits_and_costs():
    report = reconcile_vendor_fill_events(blueprint(), ledgers(), sources())
    assert report["total_vendor_fill_events"] == 8
    assert report["total_reconstructed_vendor_trades"] == 2
    assert report["status"] == "SUPPLIED_FILL_LEDGER_CONSISTENCY_UNVERIFIED"
    assert report["vendor_process_execution_attested"] is False
    assert report["vendor_fill_origin_authenticated"] is False
    assert report["strategy_research_accepted"] is False


def test_reproducibility_under_engine_dictionary_reordering():
    values = sources()
    reverse = {"nautilus": values["nautilus"], "lean": values["lean"]}
    assert reconcile_vendor_fill_events(
        blueprint(), ledgers(), values) == reconcile_vendor_fill_events(
        blueprint(), ledgers(), reverse)


@pytest.mark.parametrize("engine", ["lean", "nautilus"])
def test_missing_source_engine_events_never_silently_skipped(engine):
    values = sources()
    del values[engine]
    with pytest.raises(ValueError, match="Every planned"):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)


def test_missing_second_exit_and_fake_extra_event_rejected():
    values = sources()
    values["lean"] = events()[:-1]
    with pytest.raises(ValueError, match="quantities"):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)
    values = sources()
    extra = dict(events()[-1], fill_id="UNKNOWN", trade_id="other")
    values["lean"] = events() + [extra]
    with pytest.raises(ValueError, match="Orphan"):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)


def test_duplicate_source_fill_and_reverse_action_rejected():
    values = sources()
    values["lean"] = events() + [events()[-1]]
    with pytest.raises(ValueError, match="Duplicate"):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)
    values = sources()
    values["lean"][2]["action"] = "BUY"
    with pytest.raises(ValueError, match="Exit order"):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)


def test_wrong_price_with_equal_quantities_rejected():
    values = sources()
    values["lean"][1]["price"] += 0.5
    with pytest.raises(ValueError, match="VWAP"):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)


def test_wrong_fee_or_nonfinite_input_rejected():
    values = sources()
    values["lean"][1]["fee_usd"] = 0.2
    with pytest.raises(ValueError, match="fees disagree"):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)
    values = sources()
    values["lean"][0]["price"] = float("nan")
    with pytest.raises(ValueError, match="nonfinite"):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)


def test_entry_after_exit_or_reversed_timestamp_rejected():
    values = sources()
    values["lean"][1]["phase"] = "EXIT"
    with pytest.raises(ValueError):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)
    values = sources()
    values["lean"][1]["at"] = "2026-01-05T09:59:00Z"
    with pytest.raises(ValueError, match="time order"):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)


def test_naive_time_and_boolean_quantity_rejected():
    values = sources()
    values["lean"][0]["at"] = "2026-01-05T10:01:00"
    with pytest.raises(ValueError, match="timestamp"):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)
    values = sources()
    values["lean"][0]["quantity"] = True
    with pytest.raises(ValueError, match="real number"):
        reconcile_vendor_fill_events(blueprint(), ledgers(), values)


def test_missing_trades_unverified_not_vendor_proof():
    plan = blueprint()
    empty = ledger().iloc[0:0].copy()
    data = {engine: empty.copy() for engine in ("norisk_quant", "lean", "nautilus")}
    report = reconcile_vendor_fill_events(plan, data, {"lean": [], "nautilus": []})
    assert report["status"] == "ZERO_TRADES_UNVERIFIED"
    assert report["vendor_process_execution_attested"] is False


def test_full_native_export_conversion_and_fill_reconciliation():
    # A simple one-entry/one-exit case as required by today's native-export
    # source-shaped converters. Partial event evidence is verified separately.
    plan = blueprint()
    entry, exit_ = 2000.0, 2003.0
    normalized = ledger().copy()
    normalized.loc[0, "entry_price"] = entry
    normalized.loc[0, "exit_price"] = exit_
    normalized.loc[0, "gross_pnl"] = exit_ - entry
    normalized.loc[0, "net_pnl"] = exit_ - entry - .4
    short_events = [
        dict(fill_id="A", trade_id="sweep_001",
             at="2026-01-05T10:01:00Z", action="BUY", phase="ENTRY",
             quantity=1., price=entry, fee_usd=.2),
        dict(fill_id="B", trade_id="sweep_001",
             at="2026-01-05T10:07:00Z", action="SELL", phase="EXIT",
             quantity=1., price=exit_, fee_usd=.2),
    ]
    def dump(v):
        return json.dumps(v, sort_keys=True, ensure_ascii=True,
                          separators=(",", ":"), allow_nan=False).encode("ascii")
    mapping = {"A_SOURCE": {
        "trade_id": "sweep_001", "strategy": "sweep_fib",
        "signal_at": "2026-01-05T10:00:00Z",
        "stop": 1995., "target": 2008.,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }}
    lm = dump({"closedTrades": [{
        "id": "A_SOURCE", "symbols": ["XAUUSD"],
        "entryTime": "2026-01-05T10:01:00Z",
        "exitTime": "2026-01-05T10:07:00Z",
        "direction": 0, "quantity": 1.,
        "entryPrice": 2000., "exitPrice": 2003.,
        "profitLoss": 3., "totalFees": .4,
    }]})
    nmap = {"P_SOURCE": mapping["A_SOURCE"]}
    nm = dump({"index_name": "position_id", "rows": [{
        "position_id": "P_SOURCE", "instrument_id": "XAUUSD.SIM",
        "strategy_id": "sweep_fib", "entry": "BUY", "side": "FLAT",
        "quantity": "0", "peak_qty": "1",
        "avg_px_open": "2000", "avg_px_close": "2003",
        "commissions": ["0.40 USD"], "realized_pnl": "2.60 USD",
        "ts_opened": "2026-01-05T10:01:00Z",
        "ts_closed": "2026-01-05T10:07:00Z",
        "is_snapshot": False,
    }]})
    vendors = {}
    for engine, content, sidecar, instrument in [
        ("lean", lm, dump(mapping), "XAUUSD"),
        ("nautilus", nm, dump(nmap), "XAUUSD.SIM"),
    ]:
        vendors[engine] = NativeExport(
            engine, content, sidecar,
            hashlib.sha256(content).hexdigest(),
            hashlib.sha256(sidecar).hexdigest(),
            PINNED_VENDOR[engine], instrument)
    output = normalize_compare_and_reconcile_vendor_fills(
        plan, normalized, vendors,
        {"lean": short_events, "nautilus": short_events})
    assert output["native_export_parity"]["parity_diagnostic"]["field_discrepancy_count"] == 0
    assert output["vendor_fill_event_audit"]["total_vendor_fill_events"] == 4
    assert output["vendor_execution_attested"] is False
    assert output["research_result_accepted"] is False
