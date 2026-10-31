"""Explicit, bounded offline canonical worker for frozen historical month jobs.

Binding a private plan never runs data. Execution requires --execute, a closed
UTC month, a clean pinned checkout, a held month lock and the canonical runner.
No broker, MT5, network, prospective/OOS or profitability claims.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

try:
    from scripts import research_batch_orchestrator as lab
    from scripts.research_job_month_lease import reserve_closed_month
    from scripts.research_job_plan_snapshot import verify_plan
    from scripts.research_job_preflight import preflight_job
    from scripts.research_job_queue import ROOT
except ModuleNotFoundError as exc:
    if exc.name != "scripts":
        raise
    import research_batch_orchestrator as lab
    from research_job_month_lease import reserve_closed_month
    from research_job_plan_snapshot import verify_plan
    from research_job_preflight import preflight_job
    from research_job_queue import ROOT

SOURCE_SHA = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MONTH = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])\Z")
MAX_BYTES = 2_000_000


def _private_dir(path: Path) -> Path:
    if os.name != "posix":
        raise ValueError("Offline worker requires POSIX owner-only directories")
    if path.is_symlink():
        raise ValueError("Symlinked worker directory")
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise ValueError("Worker directory must be owner-only (0700)")
    return path


def _storage(root: Path, kind: str) -> Path:
    reports = root / "reports"
    if reports.is_symlink():
        raise ValueError("Symlinked reports directory")
    reports.mkdir(exist_ok=True)
    if not reports.is_dir():
        raise ValueError("Invalid reports directory")
    return _private_dir(reports / kind)


def _read_private(path: Path) -> bytes:
    if path.is_symlink():
        raise ValueError("Symlinked private plan")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.getuid() or info.st_mode & 0o077
                or info.st_size > MAX_BYTES):
            raise ValueError("Private plan must be regular owner-only (0600), <=2 MB")
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Oversized private plan")
    return data


def _strict(raw: bytes) -> dict:
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("Duplicate private plan JSON key")
            out[key] = value
        return out

    def reject(value):
        raise ValueError("Nonfinite private plan JSON constant")

    def finite(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("Nonfinite private plan JSON number")
        return result

    try:
        obj = json.loads(raw, object_pairs_hook=unique,
                         parse_constant=reject, parse_float=finite)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed private plan JSON") from exc
    if type(obj) is not dict:
        raise ValueError("Private plan must be a JSON object")
    return obj


def _context(root: Path, fingerprint: str, month: str) -> tuple[dict, dict]:
    if type(fingerprint) is not str or not HEX64.fullmatch(fingerprint):
        raise ValueError("Invalid frozen request fingerprint")
    if type(month) is not str or not MONTH.fullmatch(month):
        raise ValueError("Invalid UTC month")
    # verify_plan recomputes the immutable snapshot and checks exact clean HEAD.
    snapshot = verify_plan(root, fingerprint)
    matches = [s for s in snapshot["slots"] if s["month"] == month]
    if len(matches) != 1:
        raise ValueError("UTC month not present exactly once in frozen request")
    return preflight_job(root, fingerprint), matches[0]


def _validate(root: Path, fingerprint: str, month: str, plan: dict) -> tuple[int, str]:
    preflight, slot = _context(root, fingerprint, month)
    if (plan.get("source_sha256") != SOURCE_SHA
            or plan.get("engine_commit") != preflight["source_commit"]):
        raise ValueError("Private source or exact frozen engine commit mismatch")
    jobs, plan_sha = lab.expand(plan)
    start = slot["start_utc"]
    end = (date.fromisoformat(slot["end_exclusive_utc"]) - timedelta(days=1)).isoformat()
    if any(job["spec"]["start"] != start or job["spec"]["end"] != end for job in jobs):
        raise ValueError("Every canonical job must cover exactly the frozen UTC month")
    return len(jobs), plan_sha


def _bound_path(root: Path, fingerprint: str, month: str) -> Path:
    return _storage(root, "research_job_execution_plans") / (fingerprint + "." + month + ".json")


def bind_plan(root: Path, fingerprint: str, month: str, plan_path: Path) -> dict:
    """Durably freeze a PRIVATE canonical plan before observing its outcomes."""
    if not plan_path.is_absolute():
        raise ValueError("Private input plan path must be absolute")
    plan = _strict(_read_private(plan_path))
    count, plan_sha = _validate(root, fingerprint, month, plan)
    record = {"schema_version": 1, "request_fingerprint": fingerprint,
              "month": month, "plan_sha256": plan_sha, "plan": plan}
    payload = lab.canonical(record) + b"\n"
    if len(payload) > MAX_BYTES:
        raise ValueError("Bound plan exceeds 2 MB")
    target = _bound_path(root, fingerprint, month)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(target, flags, 0o600)
    except FileExistsError:
        if _read_private(target) != payload:
            raise ValueError("Existing frozen execution plan differs; never overwrite")
    else:
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            target.unlink(missing_ok=True)
            raise
    return {"status": "BOUND_NOT_EXECUTED", "plan_sha256": plan_sha,
            "defined_jobs": count, "monthly_pnl_observations": 0}


def _bound(root: Path, fingerprint: str, month: str) -> tuple[dict, int, str]:
    payload = _read_private(_bound_path(root, fingerprint, month))
    record = _strict(payload)
    if (set(record) != {"schema_version", "request_fingerprint", "month",
                        "plan_sha256", "plan"}
            or type(record["schema_version"]) is not int
            or record["schema_version"] != 1
            or record["request_fingerprint"] != fingerprint
            or record["month"] != month
            or payload != lab.canonical(record) + b"\n"):
        raise ValueError("Tampered or noncanonical bound execution plan")
    plan = record["plan"]
    count, plan_sha = _validate(root, fingerprint, month, plan)
    if record["plan_sha256"] != plan_sha:
        raise ValueError("Frozen execution plan fingerprint mismatch")
    return plan, count, plan_sha


def run_month(root: Path, fingerprint: str, month: str, *,
              execute: bool = False, max_jobs: int = 10,
              recover_verified_orphans: bool = False) -> dict:
    if type(execute) is not bool or type(max_jobs) is not int or not 1 <= max_jobs <= 20:
        raise ValueError("Explicit execution flag and max-jobs 1..20 required")
    if type(recover_verified_orphans) is not bool:
        raise ValueError("Orphan recovery flag must be boolean")
    if recover_verified_orphans and not execute:
        raise ValueError("Orphan recovery requires explicit --execute")
    plan, count, plan_sha = _bound(root, fingerprint, month)
    if not execute:
        return {"status": "VERIFIED_PLAN_ONLY_NOT_EXECUTED",
                "plan_sha256": plan_sha, "defined_jobs": count,
                "backtests_executed": 0, "monthly_pnl_observations": 0}
    with reserve_closed_month(root, fingerprint, month):
        # Recheck under the exclusive month lease before any private source read.
        plan, count, plan_sha = _bound(root, fingerprint, month)
        root_out = _storage(root, "research_job_runs")
        job_out = _private_dir(root_out / fingerprint)
        out = _private_dir(job_out / month)
        previous = os.umask(0o077)
        try:
            # Recovery is never implicit. The canonical runner re-audits
            # every orphan against source, commit, spec and all three ledgers.
            options = {"max_jobs": max_jobs}
            if recover_verified_orphans:
                options["recover_verified_orphans"] = True
            result = lab.run_plan(plan, out, **options)
        finally:
            os.umask(previous)
    return {**result, "request_fingerprint": fingerprint, "month": month,
            "plan_sha256": plan_sha, "historical_exposed_not_oos": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("bind", "run"))
    parser.add_argument("--fingerprint", required=True)
    parser.add_argument("--month", required=True)
    parser.add_argument("--plan", type=Path, help="Absolute owner-only private canonical JSON plan (bind only)")
    parser.add_argument("--execute", action="store_true", help="Explicitly authorize offline canonical execution")
    parser.add_argument("--max-jobs", type=int, default=10)
    parser.add_argument(
        "--recover-verified-orphans", action="store_true",
        help="Explicit canonical audit of complete orphan outputs; requires run --execute")
    args = parser.parse_args(argv)
    if args.action == "bind":
        if args.plan is None or args.execute or args.recover_verified_orphans:
            parser.error("bind requires --plan and forbids execution/recovery")
        result = bind_plan(ROOT, args.fingerprint, args.month, args.plan)
    else:
        if args.plan is not None:
            parser.error("run uses only the immutable bound plan, not --plan")
        result = run_month(ROOT, args.fingerprint, args.month,
                           execute=args.execute, max_jobs=args.max_jobs,
                           recover_verified_orphans=args.recover_verified_orphans)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
