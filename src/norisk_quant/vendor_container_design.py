"""Fail-closed Docker/OCI vendor launch compiler: ENGINE CONSTRUCTION ONLY.

Generates a deterministic OS argv vector for future isolated synthetic
LEAN/Nautilus research. It NEVER runs Docker, installs images, imports vendors,
opens a Gold ZIP, invokes the network, or authorizes a backtest.

The resulting command is a DESIGN artifact. The real runtime must verify the
image bytes, user-namespace policy, cgroups, seccomp profile, mounts, no network
and process exit independently before any vendor execution is permitted.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re

from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR
from norisk_quant.vendor_checkout_attestation import attest_pinned_vendor_checkout

SCHEMA = "NRFX_FROZEN_VENDOR_CONTAINER_LAUNCH_V1"
_IMAGE = re.compile(r"[a-z0-9][a-z0-9._/-]{3,127}@sha256:[0-9a-f]{64}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_ENTRIES = {
    "lean": "/nrfx/bin/lean-offline-gated-v1",
    "nautilus": "/nrfx/bin/nautilus-offline-gated-v1",
}
_SOURCE = {
    "lean": "vendor/upstream/lean",
    "nautilus": "vendor/upstream/nautilus_trader",
}


def _canon(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _directory(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ValueError("Sandbox mounts require existing absolute directories")
    if not path.is_dir():
        raise ValueError("Sandbox mount directory missing")
    current = path
    while True:
        if current.is_symlink():
            raise ValueError("Symlinked sandbox mount refused")
        if current == current.parent:
            break
        current = current.parent
    value = str(path)
    if (any(c in value for c in ",:\n\r\0")
            or not re.fullmatch(r"[/A-Za-z0-9_. -]{1,512}", value)):
        raise ValueError("Unsafe vendor sandbox mount path")
    return path


@dataclass(frozen=True, slots=True)
class VendorContainerDesign:
    engine: str
    image_by_digest: str
    frozen_parent_commit: str
    frozen_request_sha256: str
    repository_root: Path
    input_root: Path
    output_root: Path
    memory_mib: int = 2048
    cpu_count: int = 2
    pids_limit: int = 64

    def __post_init__(self) -> None:
        if (type(self.engine) is not str or self.engine not in _ENTRIES
                or type(self.image_by_digest) is not str
                or not _IMAGE.fullmatch(self.image_by_digest)
                or type(self.frozen_parent_commit) is not str
                or not _SHA.fullmatch(self.frozen_parent_commit)
                or type(self.frozen_request_sha256) is not str
                or not _HEX.fullmatch(self.frozen_request_sha256)
                or type(self.memory_mib) is not int
                or not 512 <= self.memory_mib <= 16384
                or type(self.cpu_count) is not int or not 1 <= self.cpu_count <= 8
                or type(self.pids_limit) is not int
                or not 16 <= self.pids_limit <= 128):
            raise ValueError("Invalid frozen vendor container resource/identity contract")
        for path in (self.repository_root, self.input_root, self.output_root):
            _directory(path)
        source = self.repository_root.joinpath(*_SOURCE[self.engine].split("/"))
        _directory(source)
        folders = (
            self.repository_root.resolve(),
            source.resolve(),
            self.input_root.resolve(),
            self.output_root.resolve(),
        )
        # Output cannot be anywhere inside either read-only input tree, and
        # data input cannot be nested inside the parent source checkout.
        repo, src, inp, out = folders
        if (inp == out or inp.is_relative_to(repo)
                or out.is_relative_to(repo)
                or out.is_relative_to(inp) or inp.is_relative_to(out)
                or src.is_relative_to(inp) or src.is_relative_to(out)):
            raise ValueError("Sandbox source, input and output must not overlap")
        if os.name != "posix" or not hasattr(os, "getuid") or os.getuid() == 0:
            raise ValueError("Root/Windows host may not prepare this runtime policy")


def compile_vendor_container_design(design: VendorContainerDesign) -> dict:
    """Verify the actual Gitlink and generate DOCKER ARGV ONLY (no call).

    This is not an authorization token and does not launch a container.
    The caller MUST supply a synthetic-only input folder until the owner
    explicitly changes the higher-priority ENGINE_CONSTRUCTION_ONLY rule.
    """
    if type(design) is not VendorContainerDesign:
        raise ValueError("Expected exact frozen container design")
    proof = attest_pinned_vendor_checkout(
        design.repository_root, design.engine)
    if (proof["parent_commit"] != design.frozen_parent_commit
            or proof["gitlink_commit"] != PINNED_VENDOR[design.engine]
            or proof["checkout_commit"] != PINNED_VENDOR[design.engine]
            or proof["source_checkout_clean"] is not True):
        raise ValueError("Vendor runtime Git checkout not pinned to frozen request")
    parent, source = (
        str(design.repository_root.resolve()),
        str((design.repository_root / _SOURCE[design.engine]).resolve()),
    )
    # Path "parent" is not passed as an extra Docker mount. Only source,
    # private synthetic input, and writable output enter the future process.
    argv = [
        "docker", "run", "--rm", "--pull=never",
        "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=" + str(design.pids_limit),
        "--memory=" + str(design.memory_mib) + "m",
        "--cpus=" + str(design.cpu_count),
        "--user=" + str(os.getuid()) + ":" + str(os.getgid()),
        "--ulimit=nofile=256:256",
        "--ulimit=core=0:0",
        "--tmpfs=/tmp:rw,nosuid,nodev,noexec,size=64m",
        "--mount=type=bind,src=" + source + ",dst=/nrfx/vendor,readonly",
        "--mount=type=bind,src=" + str(design.input_root.resolve())
        + ",dst=/nrfx/input,readonly",
        "--mount=type=bind,src=" + str(design.output_root.resolve())
        + ",dst=/nrfx/output",
        "--workdir=/nrfx/output",
        "--entrypoint=" + _ENTRIES[design.engine],
        design.image_by_digest,
        "--request=/nrfx/input/request.json",
        "--response=/nrfx/output/unverified.json",
    ]
    result = {
        "schema": SCHEMA,
        "status": "COMPILED_NOT_EXECUTED",
        "engine": design.engine,
        "frozen_parent_commit": design.frozen_parent_commit,
        "source_gitlink_commit": proof["gitlink_commit"],
        "image_by_digest": design.image_by_digest,
        "frozen_request_sha256": design.frozen_request_sha256,
        "argv": argv,
        "argv_sha256": hashlib.sha256(_canon(argv)).hexdigest(),
        "network_enabled": False,
        "source_and_input_read_only": True,
        "cgroup_resource_limits_requested": True,
        "image_verified_locally": False,
        "sandbox_runtime_attested": False,
        "vendor_started": False,
        "market_data_opened": False,
        "strategy_result_accepted": False,
        "engine_construction_only": True,
    }
    return {**result, "design_sha256":
            hashlib.sha256(_canon(result)).hexdigest()}
