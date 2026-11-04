"""Bounded Linux fault-injection worker supervisor (construction only).

Launches ONLY hard-coded standard-library synthetic workers, not user code,
research strategies, vendor engines, brokers or market data readers.
Enforces bounded stdout/stderr with nonblocking selectors, a wall deadline,
dedicated process group, and durable fenced /proc identity binding. After
any error it proves same-boot process group absence (fail closed otherwise).

This is NOT an untrusted-code sandbox: no seccomp, namespaces, cgroups or
pre-exec rlimits are claimed, and it must not be used to run vendor engines.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time

from scripts.durable_research_state import DurableResearchState
from scripts.durable_worker_process_supervisor import (
    LinuxProcInspector, attach_process_identity,
)

SCHEMA = "NRFX_SYNTHETIC_BOUNDED_WORKER_FAULT_PROOF_V1"
_PROTOCOL = b"NRFX-FAULT-LAB-V1 "
_MODES = frozenset({"digest", "nonzero", "flood", "stall", "stderr"})
_MAX_OUTPUT = 1024
_CHILD = r"""
import hashlib
import json
import os
import resource
import sys
import time

# Synthetic test only: intentionally no vendor code, external imports or
# access to anything except stdin and stdout/stderr.
resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
message = sys.stdin.buffer.readline(100)
if not message.startswith(b"NRFX-FAULT-LAB-V1 "):
    sys.exit(41)
mode = message[len(b"NRFX-FAULT-LAB-V1 "):].strip()
if mode == b"digest":
    data = b"NRFX-SYNTHETIC-CHILD-DATA-V1"
    payload = {"schema": "NRFX_SYNTHETIC_SHA256_V1",
               "digest": hashlib.sha256(data).hexdigest()}
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    sys.stdout.flush()
elif mode == b"nonzero":
    sys.exit(19)
elif mode == b"flood":
    # Controlled, finite 32 KB payload larger than the 1 KB host cap.
    os.write(1, b"X" * 32768)
elif mode == b"stderr":
    os.write(2, b"fixed error from synthetic subprocess\n")
    sys.exit(3)
elif mode == b"stall":
    time.sleep(30)
else:
    sys.exit(42)
"""


def _preflight(store: DurableResearchState, claim: dict, now_ms: int) -> None:
    if (not sys.platform.startswith("linux") or os.name != "posix"
            or type(store) is not DurableResearchState
            or type(claim) is not dict
            or type(now_ms) is not int or now_ms < 0):
        raise ValueError("Linux synthetic supervisor requires a fenced attempt")
    required = {"request_id", "attempt_id", "fencing_token", "worker", "attempt_no"}
    if not required.issubset(claim):
        raise ValueError("Synthetic supervisor claim missing fenced identity")
    with store._connection() as db:
        owned = store._owned(
            db, claim["request_id"], claim["attempt_id"],
            claim["fencing_token"], claim["worker"], now_ms)
        if (owned["state"] != "RUNNING"
                or owned["attempt_no"] != claim["attempt_no"]):
            raise ValueError("Synthetic supervisor requires live RUNNING lease")


def _bound_capture(proc: subprocess.Popen, *,
                   timeout_seconds: float) -> tuple[bytes, bytes, bool, bool]:
    """Read pipes without ever buffering more than 1024 bytes per stream.

    A descendant retaining pipes open is also stopped at the deadline.
    """
    deadline = time.monotonic() + timeout_seconds
    stdout = bytearray()
    stderr = bytearray()
    exceeded = False
    timed_out = False
    with selectors.DefaultSelector() as events:
        for stream, slot in ((proc.stdout, stdout), (proc.stderr, stderr)):
            os.set_blocking(stream.fileno(), False)
            events.register(stream, selectors.EVENT_READ, slot)
        while events.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            ready = events.select(timeout=min(remaining, 0.10))
            if not ready and proc.poll() is not None:
                # The group could have spawned descendants holding pipes.
                continue
            for key, _ in ready:
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    events.unregister(key.fileobj)
                    continue
                output = key.data
                if len(output) + len(chunk) > _MAX_OUTPUT:
                    exceeded = True
                    break
                output.extend(chunk)
            if exceeded:
                break
    return bytes(stdout), bytes(stderr), timed_out, exceeded


def _terminate_group(proc: subprocess.Popen) -> None:
    """Kill ONLY the controlled process session, and reap its leader."""
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    # If the group leader exited but descendants held our pipes open,
    # kill remaining descendants (they cannot outlive an existing PGID
    # without further process/session escape, which is outside this lab).
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)


def _prove_exit(inspector: LinuxProcInspector, identity,
                *, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = inspector.observe_exit(identity)
        if status == "EXITED_SAME_BOOT_NO_GROUP_MEMBERS":
            return True
        if status.startswith("UNKNOWN"):
            return False
        time.sleep(0.025)
    return False


def supervised_synthetic_fault_probe(
    store: DurableResearchState, claim: dict, *,
    now_ms: int, fault: str = "digest", wall_seconds: int = 2,
) -> dict:
    """Run one fixed synthetic child under durable fencing and output bounds.

    Returns an explicit failure classification; never requeues a lease or
    produces accepted research. Requires complete process-group exit proof.
    """
    if (type(fault) is not str or fault not in _MODES
            or type(wall_seconds) is not int or not 1 <= wall_seconds <= 5):
        raise ValueError("Only bounded hard-coded synthetic fault modes allowed")
    _preflight(store, claim, now_ms)
    inspector = LinuxProcInspector()
    with tempfile.TemporaryDirectory(prefix="nrfx-fault-lab-") as workdir:
        proc = subprocess.Popen(
            [sys.executable, "-I", "-S", "-c", _CHILD],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=workdir, close_fds=True,
            start_new_session=True, shell=False,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C",
                 "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        identity = None
        stdout = stderr = b""
        timed_out = exceeded = False
        try:
            # The child blocks on stdin until its PID/start ticks have been
            # bound under the SQLite lease, preventing a fast-exit race.
            identity = inspector.capture(proc.pid)
            attach_process_identity(
                store, claim, proc.pid, inspector, now_ms=now_ms)
            proc.stdin.write(_PROTOCOL + fault.encode("ascii") + b"\n")
            proc.stdin.flush()
            proc.stdin.close()
            stdout, stderr, timed_out, exceeded = _bound_capture(
                proc, timeout_seconds=wall_seconds)
        finally:
            _terminate_group(proc)
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()
        if identity is None or not _prove_exit(inspector, identity):
            raise ValueError("Synthetic worker OS process group exit NOT proven")
        if timed_out:
            status = "FAILED_WALL_DEADLINE"
        elif exceeded:
            status = "FAILED_OUTPUT_BOUND"
        elif proc.returncode != 0:
            status = "FAILED_NONZERO_EXIT"
        elif stderr:
            status = "FAILED_UNEXPECTED_STDERR"
        else:
            try:
                payload = json.loads(stdout)
            except (UnicodeError, ValueError) as exc:
                raise ValueError("Malformed synthetic child output") from exc
            expected = hashlib.sha256(b"NRFX-SYNTHETIC-CHILD-DATA-V1").hexdigest()
            if payload != {"schema": "NRFX_SYNTHETIC_SHA256_V1",
                           "digest": expected}:
                raise ValueError("Fixed synthetic child result mismatch")
            status = "SYNTHETIC_SUCCESS_ONLY"
    return {
        "schema": SCHEMA,
        "request_id": claim["request_id"],
        "attempt_id": claim["attempt_id"],
        "fencing_token": claim["fencing_token"],
        "boot_id": identity.boot_id, "pid": identity.pid,
        "start_ticks": identity.start_ticks,
        "fault_scenario": fault,
        "result": status,
        "exit_code": proc.returncode,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_bytes": len(stdout), "stderr_bytes": len(stderr),
        "process_group_exit_proven": True,
        "worker_claim_state_unchanged": True,
        "vendor_engine_executed": False,
        "market_data_accessed": False,
        "research_result_accepted": False,
        "automatic_retry_triggered": False,
        "sandbox_for_untrusted_code_proven": False,
    }
