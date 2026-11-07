"""Host-resident unattended XAUUSD research service (no ChatGPT sessions).

Run with an OS service manager on a machine holding the PRIVATE original Gold
ZIP. Supervises canonical director, writes health, resumes bounded time/disk
pauses, and FAILS CLOSED on evidence errors. No broker calls or live trading.
This file alone does not provision a host or install the OS service.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from scripts.bootstrap_arithmetic_training import _validate_years
from scripts.research_batch_orchestrator import exclusive_batch_lock, read_strict_json
from scripts.run_arithmetic_dispatch_training import SOURCE_SHA, _digest
from scripts.run_quant_research_platform import _safe_private_root

ROOT = Path(__file__).resolve().parents[1]
CONFIG_SCHEMA = "NRFX_UNATTENDED_RESEARCH_CONFIG_V1"
HEALTH_SCHEMA = "NRFX_UNATTENDED_RESEARCH_HEALTH_V1"
DIR_SCHEMA = "NRFX_AUTONOMOUS_TRAINING_DIRECTOR_V1"


@dataclass(frozen=True)
class Config:
    gold_zip: Path
    out: Path
    years: tuple[int, ...]
    seed: int
    target_generations: int
    step_generations: int
    proposal_count: int
    shard_size: int
    min_free_gb: int
    max_batch_wall_seconds: int
    max_total_wall_seconds: int
    max_resume_attempts: int
    poll_seconds: int
    retry_seconds: int
    max_pause_retries: int


def load_config(path: Path) -> Config:
    """Strict, small, immutable-control configuration; no executable strings."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32_768:
        raise ValueError("Unsafe or oversized private agent configuration")
    raw = read_strict_json(path)
    if type(raw) is not dict or set(raw) != {
        "schema", "gold_zip", "out", "years", "seed", "target_generations",
        "step_generations", "proposal_count", "shard_size", "min_free_gb",
        "max_batch_wall_seconds", "max_total_wall_seconds",
        "max_resume_attempts", "poll_seconds", "retry_seconds",
        "max_pause_retries",
    } or raw["schema"] != CONFIG_SCHEMA:
        raise ValueError("Unexpected unattended research configuration schema")
    for key in ("gold_zip", "out"):
        if (type(raw[key]) is not str or not raw[key]
                or not Path(raw[key]).is_absolute()):
            raise ValueError("Research data/output locations must be absolute paths")
    if type(raw["years"]) is not list:
        raise ValueError("Research years must be a sorted list")
    _validate_years(raw["years"])
    checks = {
        "seed": (0, 2**63 - 1), "target_generations": (1, 200),
        "step_generations": (1, 200), "proposal_count": (1, 128),
        "shard_size": (1, 128), "min_free_gb": (0, 128),
        "max_batch_wall_seconds": (60, 86400),
        "max_total_wall_seconds": (60, 604800),
        "max_resume_attempts": (1, 1000), "poll_seconds": (5, 300),
        "retry_seconds": (60, 86400), "max_pause_retries": (0, 1000),
    }
    for key, (lower, upper) in checks.items():
        if type(raw[key]) is not int or not lower <= raw[key] <= upper:
            raise ValueError("Invalid unattended research control: " + key)
    return Config(Path(raw["gold_zip"]), Path(raw["out"]),
                  tuple(raw["years"]), **{key: raw[key] for key in checks})


def _health(root: Path, *, status: str, verified: int = 0,
            run_count: int = 0, worker_pid: int | None = None) -> dict:
    if (type(verified) is not int or verified < 0
            or type(run_count) is not int or run_count < 0):
        raise ValueError("Invalid research health counters")
    obj = {
        "schema": HEALTH_SCHEMA, "status": status,
        "verified_generations_reported": verified,
        "supervised_worker_runs": run_count,
        "worker_pid": worker_pid,
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "training_only": True,
        "independent_oos_proven": False,
        "market_edge_confirmed": False,
        "live_trading_authorized": False,
    }
    path = root / "unattended_research_health.json"
    if path.is_symlink():
        raise ValueError("Symlinked research service status refused")
    fd, temporary = tempfile.mkstemp(prefix=".unattended-health-", dir=root)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write((json.dumps(obj, sort_keys=True, indent=2, allow_nan=False)
                          + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise ValueError("Symlinked research service status refused")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return obj


def _source_preflight(config: Config) -> None:
    source = config.gold_zip
    if (any(parent.is_symlink() for parent in (source, *source.parents))
            or not source.is_file() or source.suffix.lower() != ".zip"
            or _digest(source) != SOURCE_SHA):
        raise ValueError("Private original Gold ZIP absent or SHA mismatch")
    if source.resolve().is_relative_to(config.out.resolve()):
        raise ValueError("Market archive must remain outside service output")


def _worker_argv(config: Config) -> list[str]:
    return [
        sys.executable, "-m", "scripts.research_autonomous_director",
        "--gold-zip", str(config.gold_zip.resolve()),
        "--out", str(config.out.resolve()),
        "--years", *(str(year) for year in config.years),
        "--seed", str(config.seed),
        "--target-generations", str(config.target_generations),
        "--step-generations", str(config.step_generations),
        "--count", str(config.proposal_count),
        "--shard-size", str(config.shard_size),
        "--min-free-gb", str(config.min_free_gb),
        "--max-batch-wall-seconds", str(config.max_batch_wall_seconds),
        "--max-total-wall-seconds", str(config.max_total_wall_seconds),
        "--max-resume-attempts", str(config.max_resume_attempts),
    ]


def _director_result(root: Path, previous_mtime_ns: int | None, code: int,
                     target: int) -> tuple[str, int]:
    """A stale/crashed worker can never inherit a prior COMPLETE status."""
    file = root / "autonomous_research_status.json"
    if file.is_symlink() or not file.is_file():
        raise ValueError("Worker did not publish audited director status")
    if previous_mtime_ns is not None and file.stat().st_mtime_ns == previous_mtime_ns:
        raise ValueError("Worker left stale director status untouched")
    data = read_strict_json(file)
    if (type(data) is not dict or data.get("schema") != DIR_SCHEMA
            or data.get("training_only") is not True
            or data.get("independent_oos_proven") is not False
            or data.get("live_trading_authorized") is not False
            or type(data.get("verified_generations")) is not int
            or not 0 <= data["verified_generations"] <= target):
        raise ValueError("Invalid autonomous director evidence status")
    status = data.get("status")
    if status == "COMPLETE_HISTORICAL_TRAINING_ONLY_NOT_OOS":
        if code != 0 or data["verified_generations"] != target:
            raise ValueError("False worker completion or incomplete generation cap")
        return "TRAINING_CAP_REACHED_NOT_OOS", target
    if code != 2:
        raise ValueError("Worker exit code contradicts its progress status")
    if status in ("PAUSED_TOTAL_TIME_BUDGET", "PAUSED_DISK_BUDGET",
                  "PAUSED_RESUME_ATTEMPTS_BUDGET"):
        return status, data["verified_generations"]
    raise ValueError("Worker halted without an automatically resumable state")


def run_worker(config: Config, *, run_count: int = 1,
               launcher=None, sleeper=None) -> tuple[str, int]:
    """One supervised child. Periodic heartbeat during year-long replay."""
    if launcher is None:
        launcher = subprocess.Popen
    if sleeper is None:
        sleeper = time.sleep
    root = config.out
    marker = root / "autonomous_research_status.json"
    previous = (marker.stat().st_mtime_ns
                if marker.exists() and not marker.is_symlink() else None)
    _source_preflight(config)
    log = root / "unattended_research_worker.log"
    if log.is_symlink() or (log.exists() and not log.is_file()):
        raise ValueError("Unsafe unattended worker log")
    descriptor = os.open(log, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "ab", buffering=0) as stream:
        process = launcher(_worker_argv(config), cwd=ROOT,
                           stdin=subprocess.DEVNULL, stdout=stream, stderr=stream)
        try:
            _health(root, status="RESEARCH_RUNNING", run_count=run_count,
                    worker_pid=process.pid)
            while process.poll() is None:
                sleeper(config.poll_seconds)
                _health(root, status="RESEARCH_RUNNING", run_count=run_count,
                        worker_pid=process.pid)
            return _director_result(root, previous, process.returncode,
                                    config.target_generations)
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def serve(config: Config, *, once: bool = False,
          launcher=None, sleeper=None) -> dict:
    """Continue research between ChatGPT sessions on the installed host.

    Acquire the exclusive owner lock BEFORE touching health evidence: a second
    invocation must never overwrite a healthy running instance's heartbeat.
    """
    if sleeper is None:
        sleeper = time.sleep
    _safe_private_root(config.out)
    control = config.out / ".unattended_service_lock"
    if control.is_symlink() or (control.exists() and not control.is_dir()):
        raise ValueError("Unsafe service lock")
    control.mkdir(mode=0o700, exist_ok=True)
    with exclusive_batch_lock(control):
        pauses = 0
        runs = 0
        try:
            # A failed preflight invalidates a stale green status, but ONLY
            # after acquiring ownership of the service's exclusive lock.
            _source_preflight(config)
            while True:
                runs += 1
                phase, completed = run_worker(config, run_count=runs,
                                              launcher=launcher, sleeper=sleeper)
                if phase == "TRAINING_CAP_REACHED_NOT_OOS":
                    return _health(config.out, status=phase, verified=completed,
                                   run_count=runs)
                if once:
                    return _health(config.out, status=phase, verified=completed,
                                   run_count=runs)
                pauses += 1
                if pauses > config.max_pause_retries:
                    return _health(config.out,
                                   status="PAUSED_UNATTENDED_RETRY_BUDGET",
                                   verified=completed, run_count=runs)
                _health(config.out, status="SLEEPING_BEFORE_SAFE_RESUME",
                        verified=completed, run_count=runs)
                sleeper(config.retry_seconds)
        except Exception:
            _health(config.out, status="FAULT_REQUIRES_EVIDENCE_REVIEW",
                    run_count=max(runs, 1))
            raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "once", "status"))
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if args.action == "status":
        status = read_strict_json(config.out / "unattended_research_health.json")
        print(json.dumps(status, indent=2, sort_keys=True))
        return 0
    report = serve(config, once=args.action == "once")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "TRAINING_CAP_REACHED_NOT_OOS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
