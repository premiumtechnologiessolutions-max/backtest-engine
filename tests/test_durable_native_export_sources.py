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


def test_vendor_source_receipts_survive_wal_backup_and_review_only_restore(tmp_path):
    from scripts.durable_backup_attestation import (
        backup_durable_state, restore_durable_backup, verify_durable_backup)
    from scripts.durable_operations_gate import evaluate
    state, claim, blueprint, ledger, vendors = setup(tmp_path)
    stage_native_source_evidence(
        state, claim, blueprint, ledger, vendors, now_ms=1200)
    root = tmp_path / "backups"
    root.mkdir()
    saved = backup_durable_state(
        state.database, root, "native_source_backup", now_ms=1300)
    assert saved["worker_started"] is False
    verified = verify_durable_backup(root / "native_source_backup")
    assert verified["resume_automatically_authorized"] is False
    target = tmp_path / "recovered.sqlite3"
    restored = restore_durable_backup(
        root / "native_source_backup", target)
    assert restored["automatic_resume"] is False
    recovered = DurableResearchState(target)
    source_audit = audit_native_source_evidence(recovered)
    assert source_audit["reports"] == 1
    assert source_audit["vendor_exports"] == 1
    assert recovered.status(claim["request_id"])["state"] == "RECONCILING"
    code, report = evaluate(recovered.database, now_ms=1300)
    assert code == 2
    assert report["native_source_evidence"]["accepted"] == 0



def test_atomic_native_source_failure_rolls_back_parity_and_source(tmp_path):
    """An injected failure in write #2 MUST roll back write #1."""
    import sqlite3
    from scripts.durable_cross_engine_parity import _table as parity_table
    from scripts.durable_native_export_sources import _schema as source_table
    state, claim, blueprint, ledger, vendors = setup(tmp_path)
    with state._write() as db:
        parity_table(db)
        source_table(db)
        db.execute(
            "CREATE TRIGGER synthetic_source_disk_failure "
            "BEFORE INSERT ON unverified_native_export_sources "
            "BEGIN SELECT RAISE(ABORT, 'injected source write failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected source"):
        stage_native_source_evidence(
            state, claim, blueprint, ledger, vendors, now_ms=1200)
    with state._connection() as db:
        assert db.execute(
            "SELECT COUNT(*) FROM unverified_cross_engine_parity"
        ).fetchone()[0] == 0
        assert db.execute(
            "SELECT COUNT(*) FROM unverified_native_export_sources"
        ).fetchone()[0] == 0
    assert state.status(claim["request_id"])["state"] == "RECONCILING"


def test_preexisting_parity_without_vendor_source_requires_manual_review(tmp_path):
    from scripts.durable_cross_engine_parity import (
        stage_unverified_cross_engine_parity,
        audit_unverified_cross_engine_parity,
    )
    from norisk_quant.native_export_parity_pipeline import _build_native_export_parity
    state, claim, blueprint, ledger, vendors = setup(tmp_path)
    _, ledgers = _build_native_export_parity(blueprint, ledger, vendors)
    stage_unverified_cross_engine_parity(
        state, claim, blueprint, ledgers, now_ms=1200)
    with pytest.raises(ValueError, match="Incomplete existing parity/source"):
        stage_native_source_evidence(
            state, claim, blueprint, ledger, vendors, now_ms=1201)
    assert audit_unverified_cross_engine_parity(state)["reports"] == 1
    assert audit_native_source_evidence(state)["reports"] == 0


def test_concurrent_atomic_native_stage_is_single_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from scripts.durable_cross_engine_parity import audit_unverified_cross_engine_parity
    state, claim, blueprint, ledger, vendors = setup(tmp_path)
    def stage(_):
        return stage_native_source_evidence(
            state, claim, blueprint, ledger, vendors, now_ms=1200)["status"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(stage, range(8)))
    assert results.count("STAGED_UNVERIFIED") == 1
    assert results.count("ALREADY_STAGED_UNVERIFIED") == 7
    assert audit_unverified_cross_engine_parity(state)["reports"] == 1
    assert audit_native_source_evidence(state)["reports"] == 1


def test_expired_fenced_native_attempt_does_not_write_either_receipt(tmp_path):
    from scripts.durable_cross_engine_parity import audit_unverified_cross_engine_parity
    state, claim, blueprint, ledger, vendors = setup(tmp_path)
    with pytest.raises(ValueError, match="Stale or unauthorized"):
        stage_native_source_evidence(
            state, claim, blueprint, ledger, vendors, now_ms=11001)
    assert audit_unverified_cross_engine_parity(state)["reports"] == 0
    assert audit_native_source_evidence(state)["reports"] == 0


def test_atomic_manifest_and_parity_are_frozen_to_same_attempt(tmp_path):
    state, claim, blueprint, ledger, vendors = setup(tmp_path)
    result = stage_native_source_evidence(
        state, claim, blueprint, ledger, vendors, now_ms=1200)
    assert result["atomic_two_receipt_commit"] is True
    with state._connection() as db:
        row = db.execute(
            "SELECT p.attempt_id AS pa,s.attempt_id AS sa,"
            "p.report_sha256 AS ph,s.parity_sha256 AS sh,"
            "p.fencing_token AS pt,s.fencing_token AS st "
            "FROM unverified_cross_engine_parity p JOIN "
            "unverified_native_export_sources s ON s.attempt_id=p.attempt_id"
        ).fetchone()
    assert row["pa"] == row["sa"] == claim["attempt_id"]
    assert row["ph"] == row["sh"] == result["parity_report_sha256"]
    assert row["pt"] == row["st"] == claim["fencing_token"]



def synthetic_vendor_fills():
    return {"lean": [
        {
            "fill_id": "L-E1", "trade_id": "T001",
            "at": "2026-01-02T10:01:00Z", "action": "BUY",
            "phase": "ENTRY", "quantity": 0.25, "price": 2000.0,
            "fee_usd": 0.05,
        },
        {
            "fill_id": "L-E2", "trade_id": "T001",
            "at": "2026-01-02T10:01:00Z", "action": "BUY",
            "phase": "ENTRY", "quantity": 0.75, "price": 2000.0,
            "fee_usd": 0.15,
        },
        {
            "fill_id": "L-X1", "trade_id": "T001",
            "at": "2026-01-02T10:05:00Z", "action": "SELL",
            "phase": "EXIT", "quantity": 1.0, "price": 2003.0,
            "fee_usd": 0.2,
        },
    ]}


def test_fill_reconciliation_is_part_of_same_fenced_atomic_source_receipt(tmp_path):
    from scripts.durable_cross_engine_parity import audit_unverified_cross_engine_parity
    state, claim, blueprint, ledger, vendor = setup(tmp_path)
    result = stage_native_source_evidence(
        state, claim, blueprint, ledger, vendor, now_ms=1200,
        fill_events_by_engine=synthetic_vendor_fills())
    assert result["atomic_two_receipt_commit"] is True
    assert result["fill_event_accounting_checked"] is True
    assert result["fill_event_origin_authenticated"] is False
    assert audit_unverified_cross_engine_parity(state)["reports"] == 1
    audit = audit_native_source_evidence(state)
    assert audit["reports"] == 1
    assert audit["fill_event_reports"] == 1
    assert audit["fill_events_checked"] == 3
    assert audit["accepted"] == 0
    assert stage_native_source_evidence(
        state, claim, blueprint, ledger, vendor, now_ms=1201,
        fill_events_by_engine=synthetic_vendor_fills()
    )["status"] == "ALREADY_STAGED_UNVERIFIED"


def test_partial_fill_mismatch_rejects_both_receipts_before_db_write(tmp_path):
    from scripts.durable_cross_engine_parity import audit_unverified_cross_engine_parity
    state, claim, blueprint, ledger, vendor = setup(tmp_path)
    fills = synthetic_vendor_fills()
    fills["lean"][1]["quantity"] = 0.5
    with pytest.raises(ValueError, match="quantities"):
        stage_native_source_evidence(
            state, claim, blueprint, ledger, vendor, now_ms=1200,
            fill_events_by_engine=fills)
    assert audit_native_source_evidence(state)["reports"] == 0
    assert audit_unverified_cross_engine_parity(state)["reports"] == 0


def test_forged_fill_metadata_fails_audit_even_if_outer_sha_is_recomputed(tmp_path):
    import json
    import hashlib
    state, claim, blueprint, ledger, vendor = setup(tmp_path)
    stage_native_source_evidence(
        state, claim, blueprint, ledger, vendor, now_ms=1200,
        fill_events_by_engine=synthetic_vendor_fills())
    with state._write() as db:
        original = db.execute(
            "SELECT manifest_json FROM unverified_native_export_sources"
        ).fetchone()["manifest_json"]
        body = json.loads(original)
        body["fill_event_report"]["per_vendor"]["lean"]["validated_fill_events"] = 4
        payload = json.dumps(
            body, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False)
        checksum = hashlib.sha256(payload.encode("ascii")).hexdigest()
        db.execute(
            "UPDATE unverified_native_export_sources "
            "SET manifest_json=?, manifest_sha256=? WHERE attempt_id=?",
            (payload, checksum, claim["attempt_id"]))
    with pytest.raises(ValueError, match="fill audit"):
        audit_native_source_evidence(state)


def test_hash_only_fills_do_not_masquerade_as_real_vendor_execution(tmp_path):
    state, claim, blueprint, ledger, vendor = setup(tmp_path)
    stage_native_source_evidence(
        state, claim, blueprint, ledger, vendor, now_ms=1200,
        fill_events_by_engine=synthetic_vendor_fills())
    with state._connection() as db:
        body = db.execute(
            "SELECT manifest_json FROM unverified_native_export_sources"
        ).fetchone()["manifest_json"]
    assert "2000" not in body and "2003" not in body
    assert '"fill_event_origin_authenticated":false' in body
    assert '"vendor_execution_attested":false' in body
    assert '"research_result_accepted":false' in body


def test_fill_stage_fails_closed_when_second_write_is_injected_to_fail(tmp_path):
    import sqlite3
    from scripts.durable_native_export_sources import _schema as source_schema
    from scripts.durable_cross_engine_parity import (
        _table as parity_schema, audit_unverified_cross_engine_parity)
    state, claim, blueprint, ledger, vendor = setup(tmp_path)
    with state._write() as db:
        source_schema(db)
        parity_schema(db)
        db.execute(
            "CREATE TRIGGER simulated_fill_source_failure "
            "BEFORE INSERT ON unverified_native_export_sources "
            "BEGIN SELECT RAISE(ABORT, 'source write aborted'); END")
    with pytest.raises(sqlite3.IntegrityError, match="source write aborted"):
        stage_native_source_evidence(
            state, claim, blueprint, ledger, vendor, now_ms=1200,
            fill_events_by_engine=synthetic_vendor_fills())
    assert audit_unverified_cross_engine_parity(state)["reports"] == 0
    assert audit_native_source_evidence(state)["reports"] == 0


def test_fill_event_counts_flow_through_mission_control_status(tmp_path):
    from norisk_quant.construction_mission_control import construction_snapshot
    from norisk_quant.campaign_sharding import freeze_sharded_campaign
    state, claim, blueprint, ledger, vendor = setup(tmp_path)
    stage_native_source_evidence(
        state, claim, blueprint, ledger, vendor, now_ms=1200,
        fill_events_by_engine=synthetic_vendor_fills())
    # Mission control requires a sharded design, not a flat vendor blueprint.
    frozen = freeze_sharded_campaign(blueprint["normalized_spec"])
    shown = construction_snapshot(
        frozen, database=state.database, now_ms=1300)
    health = shown["operational_health"]
    assert health["unverified_fill_audits"] == 1
    assert health["synthetic_fill_events_checked"] == 3
    assert shown["market_research_authorized"] is False
    assert shown["engineering_acceptance_passed"] is False



def test_fill_event_evidence_survives_wal_backup_without_resuming_workers(tmp_path):
    from scripts.durable_backup_attestation import (
        backup_durable_state, restore_durable_backup, verify_durable_backup)
    from scripts.durable_operations_gate import evaluate
    state, claim, blueprint, ledger, vendors = setup(tmp_path)
    stage_native_source_evidence(
        state, claim, blueprint, ledger, vendors, now_ms=1200,
        fill_events_by_engine=synthetic_vendor_fills())
    root = tmp_path / "protected_snapshots"
    root.mkdir()
    saved = backup_durable_state(
        state.database, root, "fills_001", now_ms=1300)
    assert saved["worker_started"] is False
    verified = verify_durable_backup(root / "fills_001")
    assert verified["resume_automatically_authorized"] is False
    restored_path = tmp_path / "restored-fill-ledger.sqlite3"
    recovered_result = restore_durable_backup(
        root / "fills_001", restored_path)
    assert recovered_result["automatic_resume"] is False
    recovered = DurableResearchState(restored_path)
    proof = audit_native_source_evidence(recovered)
    assert proof["fill_event_reports"] == 1
    assert proof["fill_events_checked"] == 3
    assert proof["accepted"] == 0
    assert recovered.status(claim["request_id"])["state"] == "RECONCILING"
    code, health = evaluate(recovered.database, now_ms=1300)
    assert code == 2
    assert health["native_source_evidence"]["fill_event_reports"] == 1
    assert health["native_source_evidence"]["accepted"] == 0
