"""Synthetic-only source evidence persisted across parity, attempt and audit."""
import hashlib
import json
import pandas as pd
import pytest

from norisk_quant.campaign_blueprint import freeze_blueprint
from norisk_quant.native_export_parity_pipeline import NativeExport
from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR
from scripts.durable_research_state import DurableResearchState
from scripts.research_job_queue import _canonical
from scripts.durable_native_export_sources import (
    stage_native_source_evidence, audit_native_source_evidence,
)


def raw(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def setup(tmp_path):
    blueprint = freeze_blueprint({
        "source_commit": "a" * 40,
        "dataset": {"id": "xauusd_m1", "archive_sha256": "b" * 64,
                    "start": "2026-01-01", "end": "2026-01-31",
                    "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2026-01-01", "end": "2026-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [{"id": "bos_fib", "code_sha256": "c" * 64,
                        "spec_sha256": "d" * 64}],
        "execution_engines": ["norisk_quant", "lean"],
        "ai_reviewers": [],
        "resource_limits": {"max_workers": 1, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.4,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    })
    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/example.md",
        "frozen_spec_sha256": "1" * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40, "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31", "status": "QUEUED_NOT_EXECUTED",
    }
    request = {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}
    state = DurableResearchState(tmp_path / "state.sqlite3")
    state.ingest_record(request)
    claim = state.claim_next("synthetic-worker", now_ms=1000, lease_seconds=10)
    state.start_reconciliation(
        claim["request_id"], claim["attempt_id"],
        claim["fencing_token"], claim["worker"], now_ms=1100)
    source = raw({"closedTrades": [{
        "id": "L001", "symbols": ["XAUUSD"],
        "entryTime": "2026-01-02T10:01:00Z",
        "exitTime": "2026-01-02T10:05:00Z",
        "direction": 0, "quantity": 1,
        "entryPrice": 2000, "exitPrice": 2003,
        "profitLoss": 3, "totalFees": .4,
    }]})
    side = raw({"L001": {
        "trade_id": "T001", "strategy": "bos_fib",
        "signal_at": "2026-01-02T10:00:00Z",
        "stop": 1995, "target": 2005,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }})
    export = NativeExport(
        "lean", source, side, hashlib.sha256(source).hexdigest(),
        hashlib.sha256(side).hexdigest(), PINNED_VENDOR["lean"], "XAUUSD",
    )
    ledger = pd.DataFrame([{
        "trade_id": "T001", "strategy": "bos_fib",
        "signal_at": "2026-01-02T10:00:00Z",
        "entry_at": "2026-01-02T10:01:00Z",
        "closed_at": "2026-01-02T10:05:00Z",
        "side": 1, "entry_price": 2000., "exit_price": 2003.,
        "stop": 1995., "target": 2005., "ounces": 1.,
        "gross_pnl": 3., "cost": .4, "net_pnl": 2.6,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }])
    return state, claim, blueprint, ledger, {"lean": export}


def test_full_synthetic_export_to_fenced_durable_source(tmp_path):
    state, claim, blueprint, ledger, vendor = setup(tmp_path)
    first = stage_native_source_evidence(
        state, claim, blueprint, ledger, vendor, now_ms=1200)
    assert first["status"] == "STAGED_UNVERIFIED"
    second = stage_native_source_evidence(
        state, claim, blueprint, ledger, vendor, now_ms=1201)
    assert second["status"] == "ALREADY_STAGED_UNVERIFIED"
    assert audit_native_source_evidence(state)["vendor_exports"] == 1
    assert state.status(claim["request_id"])["state"] == "RECONCILING"
    assert first["accepted"] is False


def test_mutated_database_source_manifest_is_rejected(tmp_path):
    state, claim, blueprint, ledger, vendor = setup(tmp_path)
    stage_native_source_evidence(
        state, claim, blueprint, ledger, vendor, now_ms=1200)
    with state._write() as db:
        db.execute(
            "UPDATE unverified_native_export_sources SET manifest_json='{}'"
            " WHERE attempt_id=?", (claim["attempt_id"],))
    with pytest.raises(ValueError, match="Altered"):
        audit_native_source_evidence(state)


def test_stale_attempt_cannot_stage_vendor_source(tmp_path):
    state, claim, blueprint, ledger, vendor = setup(tmp_path)
    stale = dict(claim, fencing_token=claim["fencing_token"] + 1)
    with pytest.raises(ValueError):
        stage_native_source_evidence(
            state, stale, blueprint, ledger, vendor, now_ms=1200)
    assert audit_native_source_evidence(state)["reports"] == 0


def test_vendor_source_manifest_does_not_store_prices(tmp_path):
    state, claim, blueprint, ledger, vendor = setup(tmp_path)
    stage_native_source_evidence(
        state, claim, blueprint, ledger, vendor, now_ms=1200)
    with state._connection() as db:
        data = db.execute(
            "SELECT manifest_json FROM unverified_native_export_sources"
        ).fetchone()[0]
    assert "2000" not in data and "2003" not in data
    assert "entryPrice" not in data


def test_control_plane_inspects_new_native_sources(tmp_path):
    from scripts.durable_operations_gate import evaluate
    state, claim, blueprint, ledger, vendors = setup(tmp_path)
    stage_native_source_evidence(
        state, claim, blueprint, ledger, vendors, now_ms=1200)
    code, report = evaluate(state.database, now_ms=1300)
    assert code == 2
    assert report["native_source_evidence"]["reports"] == 1
    assert report["native_source_evidence"]["vendor_exports"] == 1
    assert report["native_source_evidence"]["accepted"] == 0


def test_invalid_native_source_poisoned_control_plane(tmp_path):
    from scripts.durable_operations_gate import evaluate
    state, claim, blueprint, ledger, vendors = setup(tmp_path)
    stage_native_source_evidence(
        state, claim, blueprint, ledger, vendors, now_ms=1200)
    with state._write() as db:
        db.execute(
            "UPDATE unverified_native_export_sources "
            "SET manifest_sha256=? WHERE attempt_id=?",
            ("0" * 64, claim["attempt_id"]))
    code, report = evaluate(state.database, now_ms=1300)
    assert code == 3 and report["status"] == "INVALID"
