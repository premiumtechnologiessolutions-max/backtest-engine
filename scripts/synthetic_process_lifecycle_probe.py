"""Real Linux process-identity rehearsal with a FIXED synthetic child only.

This never starts a research engine, market-data reader, provider or user
program. A short-lived isolated process computes SHA256 of a built-in fixed
marker while the existing SQLite fencing/OS identity system verifies its PID,
start ticks, process group and eventual exit. It does NOT grant execution
authority to other scripts or provide a secure sandbox for arbitrary code.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from scripts.durable_research_state import DurableResearchState
from scripts.durable_worker_process_supervisor import (
    LinuxProcInspector, attach_process_identity,
)

SCHEMA = "NRFX_SYNTHETIC_WORKER_LIFECYCLE_PROBE_V1"
_MARKER = b"NRFX-SYNTHETIC-PROCESS-LIFECYCLE-V1\n"
_CHILD = r"""
import hashlib
import json
import resource
import sys

# Applies ONLY to this fixed synthetic health-check process, not to
# external research engines. An actual sandbox must enforce pre-exec
# limits, network namespace/cgroup policies and credential isolation.
resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
data = sys.stdin.buffer.read(4096)
if data != b"NRFX-SYNTHETIC-PROCESS-LIFECYCLE-V1\n":
    sys.exit(9)
print(json.dumps({"schema": "NRFX_SYNTHETIC_SHA256_V1",
                  "digest": hashlib.sha256(data).hexdigest()},
                 sort_keys=True, separators=(",", ":")))
"""


def _stop_group(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate(timeout=5)


def synthetic_process_lifecycle_probe(
    store: DurableResearchState, claim: dict, *,
    now_ms: int,
    timeout_seconds: int = 5,
    mode: str = "ENGINEERING_SYNTHETIC_ONLY",
) -> dict:
    """Prove real same-boot process exit after attaching a frozen lease.

    The only possible child payload is the in-code constant _MARKER, with
    no path/command/market source argument. Callers must already hold a
    synthetic/research-queue claim; its state is NOT changed by this method.
    """
    if (not sys.platform.startswith("linux") or os.name != "posix"
            or type(store) is not DurableResearchState
            or type(claim) is not dict
            or type(now_ms) is not int or now_ms < 0
            or type(timeout_seconds) is not int
            or not 1 <= timeout_seconds <= 10
            or mode != "ENGINEERING_SYNTHETIC_ONLY"):
        raise ValueError("Fixed Linux construction rehearsal only")
    fields = ("request_id", "attempt_id", "fencing_token",
              "worker", "attempt_no")
    if any(field not in claim for field in fields):
        raise ValueError("Missing fenced synthetic claim")
    # Read-only preflight before a process can be spawned. Atomic re-check
    # when attach_process_identity() enters BEGIN IMMEDIATE.
    with store._connection() as db:
        owner = store._owned(
            db, claim["request_id"], claim["attempt_id"],
            claim["fencing_token"], claim["worker"], now_ms)
        if (owner["state"] != "RUNNING"
                or owner["attempt_no"] != claim["attempt_no"]):
            raise ValueError("Cannot rehearse with non-running attempt")
    inspector = LinuxProcInspector()
    with tempfile.TemporaryDirectory(prefix="nrfx-synthetic-process-") as root:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", _CHILD],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=root,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C",
                 "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            start_new_session=True,
            shell=False,
            close_fds=True,
        )
        try:
            identity = inspector.capture(proc.pid)
            binding = attach_process_identity(
                store, claim, proc.pid, inspector, now_ms=now_ms)
            try:
                stdout, stderr = proc.communicate(
                    input=_MARKER, timeout=timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                raise ValueError("Fixed synthetic child exceeded wall deadline") from exc
            if (proc.returncode != 0 or len(stdout) > 1024
                    or len(stderr) > 1024 or stderr):
                raise ValueError("Fixed synthetic child exited abnormally")
            try:
                result = json.loads(stdout.decode("ascii"))
            except (ValueError, UnicodeError) as exc:
                raise ValueError("Malformed fixed synthetic child output") from exc
            if result != {
                "schema": "NRFX_SYNTHETIC_SHA256_V1",
                "digest": hashlib.sha256(_MARKER).hexdigest(),
            }:
                raise ValueError("Fixed synthetic lifecycle digest mismatch")
            if inspector.observe_exit(identity) != "EXITED_SAME_BOOT_NO_GROUP_MEMBERS":
                raise ValueError("Synthetic worker group exit not proven")
        finally:
            _stop_group(proc)
    return {
        "schema": SCHEMA,
        "request_id": claim["request_id"],
        "attempt_id": claim["attempt_id"],
        "fencing_token": claim["fencing_token"],
        "boot_id": identity.boot_id,
        "pid": identity.pid,
        "process_group": identity.process_group,
        "start_ticks": identity.start_ticks,
        "stored_process_binding": binding["schema"],
        "synthetic_marker_sha256": result["digest"],
        "process_group_exit_proven": True,
        "synthetic_child_started": True,
        "research_engine_started": False,
        "market_data_read": False,
        "external_provider_invoked": False,
        "arbitrary_code_execution_sandbox_proven": False,
        "network_namespace_enforced": False,
        "research_result_accepted": False,
        "automatic_requeue_triggered": False,
        "live_trading_authorized": False,
    }
