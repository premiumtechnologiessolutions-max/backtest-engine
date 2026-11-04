"""Unified read-only mission-control snapshot for Quant Engine construction.

Combines an immutable, inert campaign design with SQLite's existing
read-only health gate. It NEVER represents design as executed research or
treats successful CI as permission to run historical market jobs.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3

from norisk_quant.campaign_sharding import verify_sharded_campaign
from scripts.durable_operations_gate import evaluate as evaluate_sqlite

SCHEMA = "NRFX_QUANT_CONSTRUCTION_MISSION_CONTROL_V1"


def construction_snapshot(
    design: dict, *, database: Path | None = None,
    now_ms: int | None = None,
    backup_snapshot_dir: Path | None = None,
) -> dict:
    """Return a small structured feed ready for a later dashboard API.

    Database probing, if requested, is read-only. No model or worker starts,
    and no market data are opened. Missing DB is not reported as healthy.
    """
    frozen = verify_sharded_campaign(design)
    spec = frozen["normalized_global_spec"]
    if now_ms is not None and (type(now_ms) is not int or now_ms < 0):
        raise ValueError("Invalid observation timestamp")
    if database is None:
        health = {"status": "NOT_CONFIGURED",
                  "reason": "No durable SQLite database selected"}
        health_code = 3
    else:
        health_code, probed = evaluate_sqlite(Path(database), now_ms=now_ms)
        health = {
            "status": probed["status"],
            "reason": probed.get("reason"),
            "total_jobs": probed.get("operations", {}).get("total_jobs"),
            "by_state": probed.get("operations", {}).get("by_state"),
            "unverified_receipts": probed.get("receipt_inbox", {}).get(
                "logical_unverified_attempts"),
            "construction_campaigns": probed.get("construction_registry", {}).get("campaign_count"),
            "registered_dag_nodes": probed.get("construction_registry", {}).get("planned_nodes"),
            "unverified_parity_reports": probed.get("cross_engine_parity", {}).get("reports"),
            "cross_engine_discrepancy_fields": probed.get("cross_engine_parity", {}).get("discrepancy_fields"),
            "native_source_manifests": probed.get("native_source_evidence", {}).get("reports"),
            "native_vendor_exports": probed.get("native_source_evidence", {}).get("vendor_exports"),
            "supervisor_fault_reports": probed.get("supervisor_faults", {}).get("reports"),
            "synthetic_supervisor_failures": probed.get("supervisor_faults", {}).get("faults"),
        }
    if backup_snapshot_dir is None:
        backup = {"status": "NOT_CONFIGURED", "automatic_resume": False,
                  "manifest_verified": False}
    else:
        try:
            from scripts.durable_backup_attestation import verify_durable_backup
            verified = verify_durable_backup(Path(backup_snapshot_dir))
            backup = {"status": "VERIFIED_REVIEW_ONLY",
                      "jobs_observed": verified["jobs_observed"],
                      "attempts_observed": verified["attempts_observed"],
                      "snapshot_sha256": verified["snapshot_sha256"],
                      "automatic_resume": False, "manifest_verified": True,
                      "external_signature_verified": False}
        except (ValueError, OSError, TypeError, KeyError, sqlite3.Error):
            backup = {"status": "INVALID",
                      "reason": "backup_integrity_gate_failed",
                      "automatic_resume": False, "manifest_verified": False}
    return {
        "schema": SCHEMA,
        "project": "NO_RISK_FX_QUANT_ENGINE",
        "phase": "ENGINE_CONSTRUCTION_ONLY",
        "engine_completely_built": False,
        "engineering_acceptance_passed": False,
        "market_research_authorized": False,
        "live_trading_authorized": False,
        "market_data_opened_by_this_call": False,
        "design": {
            "sha256": frozen["sharded_blueprint_sha256"],
            "source_commit": spec["source_commit"],
            "dataset_id": spec["dataset"]["id"],
            "declared_archive_sha256": spec["dataset"]["archive_sha256"],
            "actual_archive_bytes_verified_by_this_call": False,
            "strategies_designed": frozen["strategy_count"],
            "shards_designed": frozen["shard_count"],
            "nodes_designed": frozen["total_designed_nodes"],
            "resource_limits": spec["resource_limits"],
            "static_estimates_are_not_benchmarks": True,
            "global_multiple_testing_control_complete":
                frozen["cross_shard_multiple_testing_control_implemented"],
            "reference_engines": [
                {"name": name, "status": "PLANNED_NOT_EXECUTED",
                 "runtime_integrated_and_verified": False}
                for name in spec["execution_engines"]
            ],
            "ai_reviewers": [
                {"name": name, "status": "PLANNED_NOT_EXECUTED",
                 "runtime_integrated_and_verified": False}
                for name in spec["ai_reviewers"]
            ],
        },
        "operational_health": health,
        "backup_health": backup,
        "operational_health_exit_code": health_code,
        "missing_system_wide_gates": [
            "actual_provider_runner_isolation",
            "fenced_process_supervision_full_lifecycle",
            "independent_result_acceptance",
            "global_search_multiplicity_control",
            "full_13_field_original_data_parity",
            "unified_live_dashboard",
            "security_and_recovery_release_review",
        ],
        "status": "CONSTRUCTION_NOT_COMPLETE_NO_EXECUTION",
    }
