"""Full construction-only synthetic proof of the connected Quant control plane.

Runs ONE hardcoded inert SHA256 subprocess on Linux, but NEVER executes any
vendor engine, strategy, backtest, Gold ZIP, LLM, network or broker order.
"""
import hashlib
import json
import sys

import pandas as pd

from norisk_quant.campaign_sharding import freeze_sharded_campaign
from norisk_quant.construction_mission_control import construction_snapshot
from norisk_quant.native_export_parity_pipeline import NativeExport
from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR
from scripts.durable_research_state import DurableResearchState
from scripts.durable_inert_campaign_registry import register_inert_campaign
from scripts.durable_native_export_sources import (
    stage_native_source_evidence, audit_native_source_evidence)
from scripts.durable_operations_gate import evaluate
from scripts.durable_backup_attestation import (
    backup_durable_state, restore_durable_backup)
from scripts.research_job_queue import _canonical
from scripts.synthetic_process_lifecycle_probe import synthetic_process_lifecycle_probe


def enc(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def native_source(engine, native, side_id):
    signal = {
        "trade_id": "t0001", "strategy": "sweep_fib",
        "signal_at": "2026-01-05T10:00:00Z",
        "stop": 1995, "target": 2005,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }
    sidecar = enc({side_id: signal})
    raw = enc(native)
    instrument = "XAUUSD" if engine == "lean" else "XAUUSD.SIM"
    return NativeExport(
        engine, raw, sidecar, hashlib.sha256(raw).hexdigest(),
        hashlib.sha256(sidecar).hexdigest(), PINNED_VENDOR[engine], instrument)


def construction():
    return freeze_sharded_campaign({
        "source_commit": "a" * 40,
        "dataset": {"id": "xauusd_m1", "archive_sha256": "b" * 64,
                    "start": "2026-01-01", "end": "2026-01-31",
                    "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2026-01-01", "end": "2026-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [{
            "id": "sweep_fib", "code_sha256": "c" * 64,
            "spec_sha256": "d" * 64}],
        "execution_engines": ["norisk_quant", "lean", "nautilus"],
        "ai_reviewers": ["rd_agent"],
        "resource_limits": {"max_workers": 2, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.4,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    })


def test_synthetic_entire_control_plane_recovery_without_gold_or_vendor_runs(tmp_path):
    design = construction()
    store = DurableResearchState(tmp_path / "control.sqlite3")
    registered = register_inert_campaign(store, design)
    assert registered["node_count"] == design["total_designed_nodes"]
    assert store.operational_snapshot(now_ms=900)["total_jobs"] == 0

    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/synthetic.md",
        "frozen_spec_sha256": "1" * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40,
        "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31",
        "status": "QUEUED_NOT_EXECUTED",
    }
    record = {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}
    store.ingest_record(record)
    claim = store.claim_next("construction-worker", now_ms=1000,
                             lease_seconds=10)
    if sys.platform.startswith("linux"):
        process = synthetic_process_lifecycle_probe(
            store, claim, now_ms=1200)
        assert process["process_group_exit_proven"] is True
        assert process["research_engine_started"] is False
        assert process["market_data_read"] is False
    assert store.status(claim["request_id"])["state"] == "RUNNING"
    store.start_reconciliation(
        claim["request_id"], claim["attempt_id"],
        claim["fencing_token"], claim["worker"], now_ms=1300)

    native = pd.DataFrame([{
        "trade_id": "t0001", "strategy": "sweep_fib",
        "signal_at": "2026-01-05T10:00:00Z",
        "entry_at": "2026-01-05T10:01:00Z",
        "closed_at": "2026-01-05T10:04:00Z",
        "side": 1, "entry_price": 2000., "exit_price": 2003.,
        "stop": 1995., "target": 2005., "ounces": 1.,
        "gross_pnl": 3., "cost": .4, "net_pnl": 2.6,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }])
    lean = native_source("lean", {"closedTrades": [{
        "id": "L001", "symbols": ["XAUUSD"],
        "entryTime": "2026-01-05T10:01:00Z",
        "exitTime": "2026-01-05T10:04:00Z",
        "direction": 0, "quantity": 1, "entryPrice": 2000,
        "exitPrice": 2003, "profitLoss": 3, "totalFees": .4,
    }]}, "L001")
    naut = native_source("nautilus", {
        "index_name": "position_id", "rows": [{
            "position_id": "P001", "instrument_id": "XAUUSD.SIM",
            "strategy_id": "sweep_fib", "entry": "BUY", "side": "FLAT",
            "quantity": "0", "peak_qty": "1",
            "avg_px_open": "2000", "avg_px_close": "2003",
            "commissions": ["0.40 USD"], "realized_pnl": "2.60 USD",
            "ts_opened": "2026-01-05T10:01:00Z",
            "ts_closed": "2026-01-05T10:04:00Z",
            "is_snapshot": False,
        }],
    }, "P001")
    single = design["frozen_shards"][0]["blueprint"]
    receipt = stage_native_source_evidence(
        store, claim, single, native,
        {"lean": lean, "nautilus": naut}, now_ms=1400)
    assert receipt["vendor_exports"] == 2
    assert receipt["accepted"] is False
    assert audit_native_source_evidence(store)["accepted"] == 0

    code, health = evaluate(store.database, now_ms=1500)
    assert code == 2 and health["status"] == "OPERATOR_ATTENTION"
    assert health["construction_registry"]["campaign_count"] == 1
    assert health["cross_engine_parity"]["reports"] == 1
    assert health["cross_engine_parity"]["discrepancy_fields"] == 0
    assert health["native_source_evidence"]["vendor_exports"] == 2

    root = tmp_path / "backups"
    root.mkdir()
    snapshot = backup_durable_state(
        store.database, root, "full_synthetic", now_ms=1500)
    assert snapshot["automatic_resume"] is False
    recovered_path = tmp_path / "restored.sqlite3"
    restored = restore_durable_backup(
        root / "full_synthetic", recovered_path)
    assert restored["automatic_resume"] is False
    recovered = DurableResearchState(recovered_path)
    assert recovered.status(claim["request_id"])["state"] == "RECONCILING"

    control = construction_snapshot(
        design, database=recovered.database,
        backup_snapshot_dir=root / "full_synthetic", now_ms=1500)
    assert control["design"]["strategies_designed"] == 1
    assert control["operational_health"]["construction_campaigns"] == 1
    assert control["operational_health"]["unverified_parity_reports"] == 1
    assert control["operational_health"]["native_vendor_exports"] == 2
    assert control["backup_health"]["status"] == "VERIFIED_REVIEW_ONLY"
    assert control["market_research_authorized"] is False
    assert control["engineering_acceptance_passed"] is False
    assert control["live_trading_authorized"] is False
    assert control["engine_completely_built"] is False
    # The mission-control export contains only metadata and hashes,
    # never the synthetic trade prices or original archived quotes.
    export = json.dumps(control, sort_keys=True)
    assert '"profitLoss"' not in export
    assert '"entryPrice"' not in export
