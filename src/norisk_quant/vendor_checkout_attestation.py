"""Read-only local Git source attestation for pinned external vendor checkouts.

Checks the parent commit gitlink, actual submodule HEAD, cleanliness and
selected entry-point files. This NEVER imports/executes LEAN or Nautilus,
fetches source over a network or examines original Gold market data.

Local Git state is not independent cryptographic/remote provenance:
administrator access or malicious Git objects can subvert this proof.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess

from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR

SCHEMA = "NRFX_LOCAL_VENDOR_GITLINK_ATTESTATION_V1"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_VENDORS = {
    "lean": (
        "vendor/upstream/lean",
        ("Engine/DataFeeds/SubscriptionSynchronizer.cs",
         "Engine/Results/BacktestingResultHandler.cs"),
    ),
    "nautilus": (
        "vendor/upstream/nautilus_trader",
        ("crates/backtest/src/data_iterator.rs",
         "crates/event_store/src/manifest.rs"),
    ),
}


def _git(root: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update({
        "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
    })
    try:
        output = subprocess.run(
            ["git", "-C", str(root), "-c", "core.fsmonitor=false",
             "-c", "core.hooksPath=" + os.devnull, *args],
            capture_output=True, text=True, encoding="utf-8",
            errors="strict", timeout=15, check=False, env=env,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise ValueError("Unable to inspect local vendor Git identity") from exc
    if output.returncode or len(output.stdout) > 65536 or len(output.stderr) > 65536:
        raise ValueError("Local vendor Git integrity inspection failed")
    return output.stdout.strip()


def _no_symlinks(path: Path, stop: Path) -> None:
    current = path
    while True:
        if current.is_symlink():
            raise ValueError("Symlinked vendor or checkout path refused")
        if current == stop:
            return
        if current == current.parent:
            raise ValueError("Vendor checkout escaped intended repository")
        current = current.parent


def _attest_local_gitlink(
    root: Path, relative: str, expected_sha: str,
    required_sources: tuple[str, ...],
) -> dict:
    """Testable core verifier; production caller fixes the upstream pins."""
    if (type(expected_sha) is not str or not _SHA.fullmatch(expected_sha)
            or type(relative) is not str
            or not re.fullmatch(r"vendor/upstream/[a-z][a-z0-9_]+", relative)
            or type(required_sources) is not tuple or not required_sources):
        raise ValueError("Invalid fixed vendor checkout contract")
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Missing or symlinked parent repository")
    child = root.joinpath(*relative.split("/"))
    _no_symlinks(child, root)
    if not child.is_dir():
        raise ValueError("Pinned Git checkout not materialized")
    parent_head = _git(root, "rev-parse", "--verify", "HEAD")
    if not _SHA.fullmatch(parent_head):
        raise ValueError("Invalid host commit identity")
    actual_gitlink = _git(root, "ls-tree", "--full-tree", "HEAD", "--", relative)
    match = re.fullmatch(
        r"160000 commit ([0-9a-f]{40})\t" + re.escape(relative),
        actual_gitlink,
    )
    if match is None or match.group(1) != expected_sha:
        raise ValueError("Host commit does not pin expected vendor gitlink")
    top = _git(child, "rev-parse", "--show-toplevel")
    if Path(top).resolve() != child.resolve():
        raise ValueError("Vendor files belong to a different Git repository")
    actual_head = _git(child, "rev-parse", "--verify", "HEAD")
    if actual_head != expected_sha:
        raise ValueError("Vendor checkout HEAD differs from pinned source")
    # Check untracked as well as staged and unstaged changes. Do not allow a
    # dirty *host* checkout to claim that the adapter build was frozen.
    if (_git(root, "status", "--porcelain=v1", "--untracked-files=all")
            or _git(child, "status", "--porcelain=v1", "--untracked-files=all")):
        raise ValueError("Dirty host or vendor checkout cannot be attested")
    entries = []
    for relative_source in required_sources:
        if (type(relative_source) is not str or not relative_source
                or relative_source.startswith("/")
                or "\\" in relative_source
                or ".." in Path(relative_source).parts):
            raise ValueError("Invalid pinned vendor source entry")
        file = child.joinpath(*relative_source.split("/"))
        _no_symlinks(file, child)
        if not file.is_file():
            raise ValueError("Required vendor source file is missing")
        # Ensure file is part of the pinned Git tree, not an ignored or
        # untracked local file that happens to have a familiar name.
        observed = _git(child, "ls-files", "--error-unmatch", "--", relative_source)
        if observed != relative_source:
            raise ValueError("Vendor entry point is not tracked at pinned commit")
        size = file.stat().st_size
        if not 1 <= size <= 10 * 1024 * 1024:
            raise ValueError("Missing, empty or oversized vendor source file")
        digest = hashlib.sha256(file.read_bytes()).hexdigest()
        entries.append({"path": relative_source, "source_sha256": digest})
    if (_git(root, "rev-parse", "--verify", "HEAD") != parent_head
            or _git(child, "rev-parse", "--verify", "HEAD") != expected_sha):
        raise ValueError("Git identity changed during vendor attestation")
    return {
        "schema": SCHEMA,
        "parent_commit": parent_head,
        "gitlink_commit": expected_sha,
        "checkout_commit": actual_head,
        "vendor_path": relative,
        "selected_entrypoints": entries,
        "source_checkout_clean": True,
        "remote_repo_origin_authenticated": False,
        "vendor_engine_started": False,
        "research_result_accepted": False,
    }


def attest_pinned_vendor_checkout(repository_root: Path, engine: str) -> dict:
    if type(engine) is not str or engine not in _VENDORS:
        raise ValueError("Unsupported vendor source attestation")
    path, sources = _VENDORS[engine]
    result = _attest_local_gitlink(
        Path(repository_root), path, PINNED_VENDOR[engine], sources)
    return {**result, "engine": engine}
