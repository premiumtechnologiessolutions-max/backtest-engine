"""Read-only machine health gate for No Risk FX unattended research.

Designed for a host-local cron/systemd timer or external monitoring agent.
Never interprets historical training as independently verified trading edge.
Exit 0 = expected healthy state, 2 = paused/operator attention, 3 = invalid
or stale evidence. No external network or private market data access.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from scripts.research_batch_orchestrator import read_strict_json
from scripts.research_unattended_service import HEALTH_SCHEMA, DIR_SCHEMA, load_config

RUNNING = {"RESEARCH_RUNNING", "SLEEPING_BEFORE_SAFE_RESUME"}
COMPLETE = {"TRAINING_CAP_REACHED_NOT_OOS"}
PAUSED = {"PAUSED_UNATTENDED_RETRY_BUDGET", "PAUSED_TOTAL_TIME_BUDGET",
          "PAUSED_DISK_BUDGET", "PAUSED_RESUME_ATTEMPTS_BUDGET",
          "FAULT_REQUIRES_EVIDENCE_REVIEW"}


def _pid_exists(pid: int) -> bool:
    """Probe host-local worker existence; never equate fresh JSON with liveness.

    A PID check alone does not prove process *identity* or progress; a robust
    supervisor additionally binds the spawned child and its lease. On
    unsupported hosts we fail closed instead of reporting healthy.
    """
    if type(pid) is not int or pid <= 0:
        return False
    if os.name == "posix":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # Existence is known, though ownership is not.
            return True
        except OSError:
            return False
    if os.name == "nt":
        # Unlike os.kill(pid, 0), use a non-destructive Windows process query.
        try:
            import ctypes
            import ctypes.wintypes
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.OpenProcess.argtypes = [ctypes.wintypes.DWORD,
                                         ctypes.wintypes.BOOL,
                                         ctypes.wintypes.DWORD]
            api.OpenProcess.restype = ctypes.wintypes.HANDLE
            handle = api.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            try:
                status = ctypes.wintypes.DWORD()
                api.GetExitCodeProcess.argtypes = [
                    ctypes.wintypes.HANDLE,
                    ctypes.POINTER(ctypes.wintypes.DWORD)]
                api.GetExitCodeProcess.restype = ctypes.wintypes.BOOL
                return bool(api.GetExitCodeProcess(handle, ctypes.byref(status))
                            and status.value == 259)
            finally:
                api.CloseHandle(handle)
        except (AttributeError, OSError, ValueError):
            return False
    return False


def evaluate(root: Path, *, max_age_seconds: int = 300,
             now: datetime | None = None,
             retry_seconds: int | None = None) -> tuple[int, dict]:
    if type(max_age_seconds) is not int or max_age_seconds < 1:
        raise ValueError("max_age_seconds must be a positive integer")
    if retry_seconds is not None and (type(retry_seconds) is not int or retry_seconds < 1):
        raise ValueError("retry_seconds must be a positive integer")
    path = root / "unattended_research_health.json"
    if path.is_symlink() or not path.is_file():
        return 3, {"state": "MISSING_HEALTH", "healthy": False}
    try:
        report = read_strict_json(path)
        if type(report) is not dict or report.get("schema") != HEALTH_SCHEMA:
            raise ValueError("Invalid health schema")
        if (report.get("training_only") is not True
                or report.get("independent_oos_proven") is not False
                or report.get("market_edge_confirmed") is not False
                or report.get("live_trading_authorized") is not False):
            raise ValueError("Unsafe research evidence flags")
        verified = report.get("verified_generations_reported")
        runs = report.get("supervised_worker_runs")
        if (type(verified) is not int or verified < 0
                or type(runs) is not int or runs < 1):
            raise ValueError("Invalid supervised research counters")
        state = report.get("status")
        if state not in RUNNING | COMPLETE | PAUSED:
            raise ValueError("Unknown research service state")
        updated = datetime.fromisoformat(report["updated_utc"])
        if updated.tzinfo is None:
            raise ValueError("Naive heartbeat timestamp")
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            raise ValueError("Naive reference timestamp")
        age = (reference - updated).total_seconds()
        if age < -60:
            return 3, {"state": "STALE_OR_FUTURE_HEARTBEAT", "healthy": False}
        # Terminal and paused states must not claim an active child process.
        # A stale worker PID can mislead an operator after a crash or restart.
        if state in COMPLETE | PAUSED and report.get("worker_pid") is not None:
            raise ValueError("Non-running state retains a worker PID")
        if state in COMPLETE:
            if verified < 1:
                raise ValueError("Completion without verified generations")
            # A durable green heartbeat alone is not proof of completion.
            director_path = root / "autonomous_research_status.json"
            if director_path.is_symlink() or not director_path.is_file():
                raise ValueError("Missing director completion evidence")
            director = read_strict_json(director_path)
            if (type(director) is not dict
                    or director.get("schema") != DIR_SCHEMA
                    or director.get("status") != "COMPLETE_HISTORICAL_TRAINING_ONLY_NOT_OOS"
                    or type(director.get("verified_generations")) is not int
                    or director["verified_generations"] != verified
                    or director.get("training_only") is not True
                    or director.get("independent_oos_proven") is not False
                    or director.get("market_edge_confirmed") not in (None, False)
                    or director.get("live_trading_authorized") is not False):
                raise ValueError("Director completion evidence contradicts health")
            return 0, {"state": state, "healthy": True,
                       "note": "Training cap only; independent OOS not proven"}
        if state in PAUSED:
            return 2, {"state": state, "healthy": False}
        # During configured retry sleep the service may intentionally be idle.
        # A fixed watchdog cannot infer whether that interval has elapsed.
        if state == "SLEEPING_BEFORE_SAFE_RESUME":
            # The sleep interval is known from the private host configuration.
            # A paused worker must not masquerade as a healthy live process,
            # and a sleep past its deadline is an actionable stale state.
            if retry_seconds is not None and age > retry_seconds + max_age_seconds:
                return 3, {"state": "STALE_RETRY_SLEEP", "healthy": False}
            return 2, {"state": state, "healthy": False,
                       "note": "Retry pending; inspect service and retry interval"}
        if age > max_age_seconds:
            return 3, {"state": "STALE_OR_FUTURE_HEARTBEAT", "healthy": False}
        if state == "RESEARCH_RUNNING":
            pid = report.get("worker_pid")
            if type(pid) is not int or pid <= 0:
                raise ValueError("Invalid worker PID")
            if not _pid_exists(pid):
                return 3, {"state": "WORKER_PID_NOT_ALIVE", "healthy": False}
        return 0, {"state": state, "healthy": True}
    except (ValueError, TypeError, KeyError, OverflowError, OSError):
        return 3, {"state": "INVALID_HEALTH_EVIDENCE", "healthy": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--max-age-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    code, report = evaluate(config.out, max_age_seconds=args.max_age_seconds,
                            retry_seconds=config.retry_seconds)
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
