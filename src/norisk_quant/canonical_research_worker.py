"""B06 — bounded research-only queue -> canonical frozen batch runner.

This is an *operator-triggered* offline worker, NOT a continuously running AI
agent or a live-trading integration. Canonical run_plan() owns all execution
and all trade/weekly/monthly audit. AI proposals cannot supply Python code,
orders, any backtest output or alternative cost accounting. Native Nova
strategy IDs of the form aql_<hash> are deliberately NOT executable here.

Runs must use a private local original Gold ZIP and exact committed source
manifest for a bounded, historical-only M1 window. No browser/API exposure.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
import stat
from pathlib import Path
import re
import threading
from typing import Iterator

from .research_control_plane import (
    Lease, ResearchQueue, EXTERNAL_SOURCE, SCHEMA, proposal_identity,
)
from .research_source_loader import preflight_private_gold_zip_window
from .research_source_preflight import inspect_local_checkout
from .frozen_batch_attestation import verify_frozen_batch_evidence

# Only code-implemented audited *canonical* strategy families may execute.
# No aliases, unsafe Python expressions, native agent strategy names or
# arbitrary fallbacks. Existing orchestrator independently validates again.
ALLOWED = frozenset(("m1-sweep",))
MAX_OUTPUT_JOB_BYTES = 128_000
RUN_ID = re.compile(r"[0-9a-f]{64}\Z")


def _proposal_from_payload(payload: dict) -> dict:
    if type(payload) is not dict or type(payload.get("canonical_experiment_id")) is not str:
        raise ValueError("Missing immutable canonical experiment intent")
    p = {
        "schema": SCHEMA, "producer": EXTERNAL_SOURCE, "agent": "nova",
        "campaign_id": "bound_worker",
        "asset": "XAUUSD",
    }
    for key in (
        "dataset_sha256", "engine_commit", "strategy_id", "parameters",
        "timeframe", "window_start_utc", "window_end_exclusive_utc",
        "quantity_ounces", "fee_all_in_per_ounce",
        "execution_mode", "exposure_context",
    ):
        p[key] = payload[key]
    actual, _, _ = proposal_identity(p)
    if actual != payload["canonical_experiment_id"]:
        raise ValueError("Canonical worker experiment fingerprint mismatch")
    return p


def frozen_plan_from_intent(intent: dict, *, data_zip: str | Path) -> dict:
    """Translate ONLY a frozen built-in strategy, never an AQL name.

    The deliberately restrictive first version runs a single full UTC
    calendar month M1 sweep. One run = one identifiable experiment.
    """
    from scripts import research_batch_orchestrator as batch

    p = _proposal_from_payload(intent)
    if p["strategy_id"] not in ALLOWED:
        raise ValueError("AI strategy implementation is not mapped to canonical Gold code")
    if p["timeframe"] != "M1" or p["execution_mode"] != "m1_conservative":
        raise ValueError("Only canonical conservative M1 reference execution is allowed")
    if p["exposure_context"] != "historical_exposed" or p["quantity_ounces"] != 1.0:
        raise ValueError("Historical exposed research only; fixed one-ounce execution scenario")
    start = datetime.fromisoformat(p["window_start_utc"])
    end = datetime.fromisoformat(p["window_end_exclusive_utc"])
    if start.tzinfo is None or end.tzinfo is None or start.utcoffset() != timedelta(0) or end.utcoffset() != timedelta(0):
        raise ValueError("Canonical worker windows require UTC")
    if (start.hour or start.minute or start.second or start.microsecond
            or end.hour or end.minute or end.second or end.microsecond):
        raise ValueError("Canonical strategy requires full-day UTC boundaries")
    if start.day != 1:
        raise ValueError("Only frozen full-calendar-month research is supported")
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    if end != next_month:
        raise ValueError("Canonical run must contain one full UTC calendar month")
    if end > datetime.now(timezone.utc):
        raise ValueError("No access to future or still-open monthly data")
    params = p["parameters"]
    if not isinstance(params, dict) or not set(params).issubset(batch.STRATEGY_PARAMS[p["strategy_id"]]):
        raise ValueError("Unknown canonical M1 strategy parameters")
    original = Path(data_zip)
    if (not original.is_absolute() or original.is_symlink() or not original.is_file()
            or original.suffix.lower() != ".zip"):
        raise ValueError("Expected private absolute original Gold ZIP path")
    spec = {
        "id": "research-" + intent["canonical_experiment_id"][:32],
        "strategy": p["strategy_id"], "timeframe": "M1",
        "execution": "reference", "start": start.date().isoformat(),
        "end": (end - timedelta(days=1)).date().isoformat(),
        "parameters": params,
    }
    plan = {
        "schema": batch.SCHEMA, "dataset": str(original),
        "source_sha256": p["dataset_sha256"], "engine_commit": p["engine_commit"],
        "exposure_context": "historical_exposed", "jobs": [spec], "grids": [],
    }
    jobs, _ = batch.expand(plan, limit=1)  # Independent strict validation
    if len(jobs) != 1:
        raise ValueError("Expected exactly one canonical research job")
    return plan


def preflight_queued_research(
    intent: dict, *, source_manifest: dict, data_zip: str | Path,
    checkout: str | Path,
) -> dict:
    """Read-only full source->strategy gate; does not claim a research lease."""
    proposal = _proposal_from_payload(intent)
    plan = frozen_plan_from_intent(intent, data_zip=data_zip)
    observed_head = inspect_local_checkout(checkout)
    evidence = preflight_private_gold_zip_window(
        proposal, source_manifest,
        original_gold_zip=data_zip, observed_engine_commit=observed_head,
        boundary_tolerance_minutes=4320,  # holiday/weekend market edges, <=72h
    )
    if not evidence.lineage_verified or evidence.experiment_id != intent["canonical_experiment_id"]:
        raise ValueError("Original ZIP direct lineage preflight did not verify")
    if evidence.source_sha256 != plan["source_sha256"]:
        raise ValueError("Source-to-runner original ZIP SHA changed")
    return {
        "experiment_id": evidence.experiment_id,
        "source_manifest_id": evidence.source_manifest_id,
        "engine_commit": observed_head,
        "plan": plan,
        "execution": "NONE_PREFLIGHT_ONLY",
        "independent_oos": False,
        "broker_fill_parity": False,
        "profitability_verified": False,
    }


@contextmanager
def _keep_lease_alive(queue: ResearchQueue, lease: Lease) -> Iterator[None]:
    """Refresh lease while canonical subprocess runs.

    Worker death ends the daemon thread and expires lease. If another
    worker reclaims it, the original bearer cannot finish the queue job.
    The canonical runner additionally serializes its own output directory.
    """
    stopped = threading.Event()
    lost = threading.Event()

    def pulse() -> None:
        while not stopped.wait(10):
            try:
                if not queue.heartbeat(
                    lease, now=datetime.now(timezone.utc), extend_seconds=120,
                ):
                    lost.set()
                    return
            except Exception:
                lost.set()
                return

    thread = threading.Thread(target=pulse, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=15)
        if lost.is_set():
            raise RuntimeError("Research worker lost fenced lease; results cannot be committed")


def execute_one_approved_job(
    queue: ResearchQueue, *,
    source_manifest: dict, data_zip: str | Path,
    checkout: str | Path, output_root: str | Path,
    scientific_journal=None,
) -> dict:
    """Process at most one operator-enabled queued job; no automatic daemon.

    The queue must already be explicitly RESUMED by the private operator.
    Never catches up thousands of unreviewed agent hypotheses. Failed audit
    yields a rejected research job and retains private artifacts for review.
    """
    from scripts import research_batch_orchestrator as batch
    now = datetime.now(timezone.utc)
    lease = queue.claim(worker="canonical_runner", now=now, lease_seconds=120)
    if lease is None:
        return {"status": "PAUSED_OR_EMPTY_OR_BUSY", "execution": "NONE"}
    try:
        # A large original ZIP may take longer than one lease interval to
        # preflight. Start fencing heartbeat BEFORE reading any source bytes.
        with _keep_lease_alive(queue, lease):
            intent = queue.leased_research_intent(lease, now=datetime.now(timezone.utc))
            science_chain_before = None
            if scientific_journal is not None:
                # Prevent an already rejected hypothesis from consuming
                # the private original archive or expensive runner.
                frozen = frozen_plan_from_intent(intent, data_zip=data_zip)
                verdict = scientific_journal.candidate_gate(frozen)
                if verdict["decision"] == "BLOCK_IDENTICAL_PREVIOUSLY_REJECTED":
                    raise ValueError("Previously rejected identical strategy cannot execute again")
                science_chain_before = verdict["history_chain_head"]
            checked = preflight_queued_research(
                intent, source_manifest=source_manifest, data_zip=data_zip,
                checkout=checkout,
            )
            root = Path(output_root)
            if not root.is_absolute() or root.is_symlink() or not root.is_dir():
                raise ValueError("Canonical output must be an existing private absolute directory")
            # Native NTFS ACLs are not equivalent to Unix chmod(0600/0700).
            # Restrict actual historical runner to POSIX owner-only files.
            if os.name != "posix":
                raise ValueError("Canonical research execution requires reviewed POSIX evidence permissions")
            if root.stat().st_uid != os.getuid() or stat.S_IMODE(root.stat().st_mode) & 0o077:
                raise ValueError("Private output root must be owner-only 0700")
            source_stat = Path(data_zip).stat()
            if source_stat.st_uid != os.getuid() or stat.S_IMODE(source_stat.st_mode) & 0o077:
                raise ValueError("Original Gold ZIP must be owner-only 0600")
            queue_stat = queue.path.stat()
            if queue_stat.st_uid != os.getuid() or stat.S_IMODE(queue_stat.st_mode) & 0o077:
                raise ValueError("Research queue database must be owner-only 0600")
            folder = root / lease.job_id
            if folder.is_symlink():
                raise ValueError("Unsafe canonical research output symlink")
            # The canonical orchestrator checks source SHA, exact Git HEAD,
            # frozen plan, trades/month/week, and independent accounting.
            result = batch.run_plan(
                checked["plan"], folder, max_jobs=1,
                dry_run=False, recover_verified_orphans=False,
            )
        if result["executed_this_invocation"] != 1 or result["reconciled_jobs"] != 1:
            raise ValueError("Canonical runner did not reconcile one fresh research ledger")
        # Independently re-read the original frozen plan and on-disk
        # trade/week/month files; do not trust run_plan's claimed counters.
        # This is still historical reference-model consistency, NOT OOS
        # or verified real broker fills.
        attestation = verify_frozen_batch_evidence(
            checked["plan"], folder,
            expected_experiment_id=lease.job_id,
            source_manifest_id=checked["source_manifest_id"],
        )
        evidence_sha = attestation.manifest_sha256
        if scientific_journal is not None:
            # If a negative study was recorded during the long runner
            # invocation, fail instead of accepting a stale eligibility gate.
            recent = scientific_journal.candidate_gate(checked["plan"])
            if (recent["decision"] == "BLOCK_IDENTICAL_PREVIOUSLY_REJECTED"
                    or recent["history_chain_head"] != science_chain_before):
                raise ValueError("Scientific decision changed during historical execution")
        accepted = queue.finish(
            lease, now=datetime.now(timezone.utc),
            result={
                "disposition": "proposal_recorded", "reason_code": "historical_audit_pending",
                "evidence_sha256": evidence_sha,
            },
        )
        if not accepted:
            raise RuntimeError("Research lease expired or revoked before evidence commit")
        return {
            "status": "HISTORICAL_RESEARCH_ARTIFACT_RECORDED_NOT_APPROVED",
            "experiment_id": lease.job_id,
            "source_manifest_id": checked["source_manifest_id"],
            "execution": "CANONICAL_M1_HISTORICAL_SIMULATION",
            "research_artifact_sha256": evidence_sha,
            "independent_oos": False, "broker_fill_parity": False,
            "profitability_verified": False, "risk_approved": False,
            "live_execution": False,
        }
    except BaseException:
        # Never requeue a failed scientific audit automatically. Require
        # explicit investigation. If lease was already lost, fencing prevents
        # older worker from declaring an outcome and standard timeout applies.
        queue.finish(
            lease, now=datetime.now(timezone.utc),
            result={
                "disposition": "rejected", "reason_code": "operator_review_required",
                "evidence_sha256": None,
            },
        )
        raise
