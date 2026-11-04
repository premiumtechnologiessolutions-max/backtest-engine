"""Synthetic durable comparison persistence: never promotes research results."""
import hashlib
import sqlite3

import pandas as pd
import pytest

from scripts.durable_research_state import DurableResearchState
from scripts.durable_cross_engine_parity import (
    stage_unverified_cross_engine_parity, audit_unverified_cross_engine_parity,
)
from scripts.research_job_queue import _canonical
from norisk_quant.campaign_blueprint import freeze_blueprint


def setup(tmp_path):
    spec = {
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
    }
    plan = freeze_blueprint(spec)
    body = {
        "schema_version": 1, "mode": "OFFLINE_RESEARCH_ONLY",
        "family": "NRF-FAC-028", "frozen_spec": "research/example.md",
        "frozen_spec_sha256": "1" * 64, "registry_sha256": "2" * 64,
        "source_commit": "a" * 40,
        "evaluation_start": "2026-01-01",
        "evaluation_end": "2026-01-31", "status": "QUEUED_NOT_EXECUTED",
    }
    frozen = {**body, "fingerprint": hashlib.sha256(_canonical(body)).hexdigest()}
    store = DurableResearchState(tmp_path / "state.sqlite3")
    store.ingest_record(frozen)
    claim = store.claim_next("synthetic-worker", lease_seconds=10, now_ms=1000)
    store.start_reconciliation(
        claim["request_id"], claim["attempt_id"], claim["fencing_token"],
        claim["worker"], now_ms=1100)
    row = {
        "trade_id": "s001", "strategy": "bos_fib",
        "signal_at": "2026-01-02T09:00:00Z",
        "entry_at": "2026-01-02T09:01:00Z",
        "closed_at": "2026-01-02T09:05:00Z",
        "side": 1, "entry_price": 2000.0, "exit_price": 2001.0,
        "stop": 1995.0, "target": 2005.0,
        "ounces": 1.0, "gross_pnl": 1.0, "cost": 0.4,
        "net_pnl": 0.6, "exit_reason": "time_exit", "gap_minutes": 0,
    }
    ledgers = {
        "norisk_quant": pd.DataFrame([row]),
        "lean": pd.DataFrame([row]),
    }
    return store, claim, plan, ledgers


def test_parity_staged_idempotently_but_never_accepted(tmp_path):
    store, claim, plan, ledgers = setup(tmp_path)
    first = stage_unverified_cross_engine_parity(
        store, claim, plan, ledgers, now_ms=1200)
    assert first["status"] == "STAGED_UNVERIFIED"
    assert first["accepted"] is False
    repeated = stage_unverified_cross_engine_parity(
        store, claim, plan, ledgers, now_ms=1201)
    assert repeated["status"] == "ALREADY_STAGED_UNVERIFIED"
    audit = audit_unverified_cross_engine_parity(store)
    assert audit["reports"] == 1
    assert audit["discrepancy_fields"] == 0
    assert audit["accepted"] == 0
    assert store.status(claim["request_id"])["state"] == "RECONCILING"


def test_immutable_parity_conflict_rejected(tmp_path):
    store, claim, plan, ledgers = setup(tmp_path)
    stage_unverified_cross_engine_parity(store, claim, plan, ledgers, now_ms=1200)
    edited = {k: v.copy() for k, v in ledgers.items()}
    # Same gross P/L but execution entry/exit prices moved.
    for field in ("entry_price", "exit_price", "stop", "target"):
        edited["lean"].loc[0, field] += 2.0
    with pytest.raises(ValueError, match="Immutable parity"):
        stage_unverified_cross_engine_parity(
            store, claim, plan, edited, now_ms=1201)
    assert audit_unverified_cross_engine_parity(store)["reports"] == 1


def test_manual_sql_mutation_fails_readonly_parity_audit(tmp_path):
    store, claim, plan, ledgers = setup(tmp_path)
    stage_unverified_cross_engine_parity(store, claim, plan, ledgers, now_ms=1200)
    with store._write() as db:
        db.execute(
            "UPDATE unverified_cross_engine_parity SET report_json='{}'"
            " WHERE attempt_id=?", (claim["attempt_id"],))
    with pytest.raises(ValueError, match="tampered"):
        audit_unverified_cross_engine_parity(store)


def test_only_matching_lease_and_frozen_window_can_stage(tmp_path):
    store, claim, plan, ledgers = setup(tmp_path)
    wrong = dict(claim, fencing_token=claim["fencing_token"] + 1)
    with pytest.raises(ValueError, match="Stale"):
        stage_unverified_cross_engine_parity(
            store, wrong, plan, ledgers, now_ms=1200)
    old = dict(plan)
    spec = dict(plan["normalized_spec"])
    spec["evaluation"] = dict(spec["evaluation"], end="2026-01-30")
    old = freeze_blueprint(spec)
    with pytest.raises(ValueError, match="does not match"):
        stage_unverified_cross_engine_parity(
            store, claim, old, ledgers, now_ms=1200)
    assert audit_unverified_cross_engine_parity(store)["reports"] == 0


def test_parity_rejected_after_attempt_lease_expiry(tmp_path):
    store, claim, plan, ledgers = setup(tmp_path)
    with pytest.raises(ValueError, match="Stale"):
        stage_unverified_cross_engine_parity(
            store, claim, plan, ledgers, now_ms=11001)
    assert audit_unverified_cross_engine_parity(store)["reports"] == 0
