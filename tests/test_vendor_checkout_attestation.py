"""Synthetic local Git repository checks; no Gold data or vendor code execution."""
import subprocess
from pathlib import Path

import pytest

from norisk_quant.vendor_checkout_attestation import (
    _attest_local_gitlink, attest_pinned_vendor_checkout,
)

pytestmark = pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="Git required for local source verification",
)


def git(directory: Path, *args: str):
    result = subprocess.run(["git", "-C", str(directory), *args],
                            capture_output=True, text=True, check=True)
    return result.stdout.strip()


def checkout(tmp_path):
    origin = tmp_path / "vendor_original"
    origin.mkdir()
    git(origin, "init", "-q")
    git(origin, "config", "user.email", "synthetic@example.invalid")
    git(origin, "config", "user.name", "Synthetic CI")
    source = origin / "Engine/DataFeeds/SubscriptionSynchronizer.cs"
    source.parent.mkdir(parents=True)
    source.write_text("// synthetic fixed source\nclass SubscriptionSynchronizer {}\n")
    git(origin, "add", ".")
    git(origin, "commit", "-qm", "Synthetic source only")
    sha = git(origin, "rev-parse", "HEAD")
    host = tmp_path / "host"
    host.mkdir()
    git(host, "init", "-q")
    git(host, "config", "user.email", "synthetic@example.invalid")
    git(host, "config", "user.name", "Synthetic CI")
    sub = host / "vendor/upstream/lean"
    sub.parent.mkdir(parents=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(sub)], check=True)
    git(host, "update-index", "--add", "--cacheinfo",
        f"160000,{sha},vendor/upstream/lean")
    git(host, "commit", "-qm", "Freeze synthetic vendor gitlink")
    return host, sub, sha


def test_clean_local_gitlink_and_tracked_entrypoint_verified(tmp_path):
    host, _, sha = checkout(tmp_path)
    report = _attest_local_gitlink(
        host, "vendor/upstream/lean", sha,
        ("Engine/DataFeeds/SubscriptionSynchronizer.cs",))
    assert report["source_checkout_clean"] is True
    assert report["checkout_commit"] == sha
    assert len(report["selected_entrypoints"]) == 1
    assert report["vendor_engine_started"] is False
    assert report["remote_repo_origin_authenticated"] is False


def test_vendor_checkout_dirty_or_removed_source_is_denied(tmp_path):
    host, sub, sha = checkout(tmp_path)
    file = sub / "Engine/DataFeeds/SubscriptionSynchronizer.cs"
    file.write_text("malicious local modification")
    with pytest.raises(ValueError, match="Dirty"):
        _attest_local_gitlink(
            host, "vendor/upstream/lean", sha,
            ("Engine/DataFeeds/SubscriptionSynchronizer.cs",))


def test_parent_gitlink_cannot_be_replaced_by_caller_pin(tmp_path):
    host, sub, sha = checkout(tmp_path)
    with pytest.raises(ValueError, match="gitlink"):
        _attest_local_gitlink(
            host, "vendor/upstream/lean", "0" * 40,
            ("Engine/DataFeeds/SubscriptionSynchronizer.cs",))


def test_nonexistent_vendor_or_untracked_source_fails(tmp_path):
    host, _, sha = checkout(tmp_path)
    with pytest.raises(ValueError):
        _attest_local_gitlink(
            host, "vendor/upstream/nautilus_trader", sha,
            ("crates/backtest/src/data_iterator.rs",))
    with pytest.raises(ValueError, match="missing"):
        _attest_local_gitlink(
            host, "vendor/upstream/lean", sha,
            ("Engine/Missing.cs",))


def test_unsafe_vendor_path_and_forged_runtime_engine_refused(tmp_path):
    host, _, sha = checkout(tmp_path)
    with pytest.raises(ValueError):
        _attest_local_gitlink(
            host, "../../secrets", sha,
            ("Engine/DataFeeds/SubscriptionSynchronizer.cs",))
    with pytest.raises(ValueError):
        attest_pinned_vendor_checkout(host, "openbb")


def test_host_dirty_file_blocks_frozen_source_claim(tmp_path):
    host, _, sha = checkout(tmp_path)
    (host / "untracked.txt").write_text("unfrozen host change")
    with pytest.raises(ValueError, match="Dirty"):
        _attest_local_gitlink(
            host, "vendor/upstream/lean", sha,
            ("Engine/DataFeeds/SubscriptionSynchronizer.cs",))
