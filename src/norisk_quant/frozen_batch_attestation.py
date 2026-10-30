"""B09: independently re-attest canonical historical batch evidence.

Worker MUST re-read durable batch manifest and independently reconcile every
frozen CSV/summary against the ONE-job plan before recording completion.
"Accepted" means internally consistent synthetic historical research;
never real broker fill, independent OOS or profitability proven.

Never execute agent code, load market prices, run a backtest, mutate output,
or communicate with a broker from this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import stat

from scripts import research_batch_orchestrator as batch

MAX_MANIFEST = 128_000
MAX_SUMMARY = 512_000
MAX_LEDGER = 64_000_000


def _strict_private_file(path: Path, *, max_bytes: int) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or unsafe canonical evidence file")
    info = path.stat()
    if info.st_nlink != 1 or not 0 < info.st_size <= max_bytes:
        raise ValueError("Unexpected size or hardlink for canonical evidence file")
    if os.name == "posix" and (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise ValueError("Canonical evidence must be owner-only 0600")


@dataclass(frozen=True)
class HistoricalAttestation:
    """Private immutable one-job ledger attestation. NOT a trading approval."""
    experiment_id: str
    frozen_job_id: str
    original_source_sha256: str
    engine_commit: str
    plan_sha256: str
    manifest_sha256: str
    source_manifest_id: str
    trades: int
    months_observed: int
    historical_exposed: bool = True
    execution: str = "CANONICAL_M1_SYNTHETIC_REFERENCE"
    independent_oos: bool = False
    brokerage_fills_verified: bool = False
    profitability_verified: bool = False
    risk_approved: bool = False
    live_execution: bool = False

    def public_status(self) -> dict:
        """Only non-sensitive scientific status. No private hashes or P/L."""
        return {
            "schema": "NRFX_HISTORICAL_LEDGER_REAUDIT_V1",
            "ledger_internal_consistency": "PASSED_ON_FROZEN_FILES",
            "execution": self.execution,
            "trades": self.trades,
            "months_observed": self.months_observed,
            "historical_exposed": True,
            "source_authentication": "NOT_VERIFIED",
            "independent_oos": False,
            "brokerage_fills_verified": False,
            "profitability_verified": False,
            "risk_approved": False,
            "live_execution": False,
        }


def verify_frozen_batch_evidence(
    frozen_plan: dict, output_directory: str | Path, *,
    expected_experiment_id: str, source_manifest_id: str,
) -> HistoricalAttestation:
    """Re-read manifest/reports and reconcile independent of worker status."""
    output = Path(output_directory)
    if output.is_symlink() or not output.is_dir():
        raise ValueError("Missing or unsafe original batch output directory")
    for value, name in (
        (expected_experiment_id, "experiment"),
        (source_manifest_id, "source manifest"),
    ):
        if (type(value) is not str or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)):
            raise ValueError(f"Expected canonical 64-digit {name} identity")
    jobs, plan_sha = batch.expand(frozen_plan, limit=1)
    if len(jobs) != 1:
        raise ValueError("Exactly one strategy plan must be audited")
    job = jobs[0]
    if frozen_plan["exposure_context"] != "historical_exposed":
        raise ValueError("No prospective claim or live execution allowed")
    if job["id"] != "research-" + expected_experiment_id[:32]:
        raise ValueError("Batch job ID differs from canonical queue experiment")
    if job["spec"]["strategy"] != "m1-sweep" or job["spec"]["timeframe"] != "M1":
        raise ValueError("Only reviewed Gold M1 sweep strategy may be attested")
    if job["spec"]["execution"] != "reference":
        raise ValueError("Fast/optimistic execution is not approved")
    manifest_file = output / "batch_manifest.json"
    _strict_private_file(manifest_file, max_bytes=MAX_MANIFEST)
    frozen_bytes = manifest_file.read_bytes()
    manifest = batch.read_strict_json(manifest_file)
    if (type(manifest) is not dict
            or set(manifest) != {"schema", "plan_sha256", "source_sha256", "engine_commit", "results"}
            or manifest["schema"] != batch.SCHEMA
            or manifest["plan_sha256"] != plan_sha
            or manifest["source_sha256"] != frozen_plan["source_sha256"]
            or manifest["engine_commit"] != frozen_plan["engine_commit"]
            or type(manifest["results"]) is not dict
            or set(manifest["results"]) != {job["id"]}):
        raise ValueError("Frozen batch manifest does not bind one exact source/plan/engine/job")
    runs = output / "runs"
    directory = runs / job["id"]
    if runs.is_symlink() or directory.is_symlink() or not directory.is_dir():
        raise ValueError("Missing or unsafe frozen research run directory")
    for name, maximum in (
        ("summary.json", MAX_SUMMARY),
        ("monthly.csv", MAX_LEDGER),
        ("weekly.csv", MAX_LEDGER),
        ("trades.csv", MAX_LEDGER),
    ):
        _strict_private_file(directory / name, max_bytes=maximum)
    original = manifest["results"][job["id"]]
    if type(original) is not dict or original.get("status") != batch.PASSED:
        raise ValueError("Failed/orphaned research run cannot be attested")
    audited = batch.audit_run(
        directory, job["spec"],
        frozen_plan["source_sha256"], frozen_plan["engine_commit"],
    )
    if audited != original:
        raise ValueError("Frozen trade/week/month evidence differs from batch manifest")
    if manifest_file.read_bytes() != frozen_bytes:
        raise ValueError("Batch manifest changed during re-audit")
    for name, key in (
        ("summary.json", "summary_sha256"),
        ("monthly.csv", "monthly_sha256"),
        ("weekly.csv", "weekly_sha256"),
        ("trades.csv", "trades_sha256"),
    ):
        if batch.file_sha(directory / name) != audited[key]:
            raise ValueError("Frozen research report mutated during re-audit")
    return HistoricalAttestation(
        experiment_id=expected_experiment_id,
        frozen_job_id=job["id"],
        original_source_sha256=frozen_plan["source_sha256"],
        engine_commit=frozen_plan["engine_commit"],
        plan_sha256=plan_sha,
        manifest_sha256=sha256(frozen_bytes).hexdigest(),
        source_manifest_id=source_manifest_id,
        trades=audited["trades"],
        months_observed=audited["months_observed"],
    )
