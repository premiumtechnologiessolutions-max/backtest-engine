"""Docker argument compilation ONLY; no Docker invocation or market data."""
import os
import sys
from pathlib import Path

import pytest

from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR
from norisk_quant import vendor_container_design as mod

pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(os, "getuid") or os.getuid() == 0,
    reason="Nonroot POSIX only",
)


def roots(tmp_path):
    repo = tmp_path / "checkout"
    source = repo / "vendor/upstream/lean"
    source.mkdir(parents=True)
    inp = tmp_path / "synthetic_input"
    out = tmp_path / "private_output"
    inp.mkdir()
    out.mkdir()
    return repo, inp, out


def design(tmp_path, **overrides):
    repo, inp, out = roots(tmp_path)
    fields = dict(
        engine="lean",
        image_by_digest="local/nrfx-lean@sha256:" + "4" * 64,
        frozen_parent_commit="a" * 40,
        frozen_request_sha256="b" * 64,
        repository_root=repo,
        input_root=inp,
        output_root=out,
    )
    fields.update(overrides)
    return mod.VendorContainerDesign(**fields)


def proof(root, engine):
    return {
        "parent_commit": "a" * 40,
        "gitlink_commit": PINNED_VENDOR[engine],
        "checkout_commit": PINNED_VENDOR[engine],
        "source_checkout_clean": True,
    }


def test_pinned_source_and_locked_down_container_argv(tmp_path, monkeypatch):
    x = design(tmp_path)
    monkeypatch.setattr(mod, "attest_pinned_vendor_checkout", proof)
    artifact = mod.compile_vendor_container_design(x)
    args = artifact["argv"]
    assert artifact["status"] == "COMPILED_NOT_EXECUTED"
    assert "--network=none" in args
    assert "--pull=never" in args
    assert "--read-only" in args
    assert "--cap-drop=ALL" in args
    assert "--security-opt=no-new-privileges:true" in args
    assert "--pids-limit=64" in args
    assert "--memory=2048m" in args
    assert "--cpus=2" in args
    assert len([a for a in args if a.startswith("--mount=")]) == 3
    assert sum(a.endswith(",readonly") for a in args) == 2
    assert args[-3] == x.image_by_digest
    assert artifact["vendor_started"] is False
    assert artifact["sandbox_runtime_attested"] is False
    assert artifact["strategy_result_accepted"] is False


def test_image_must_be_digest_pinned_not_auto_pulled(tmp_path):
    with pytest.raises(ValueError, match="resource/identity"):
        design(tmp_path, image_by_digest="local/nrfx-lean:latest")


def test_network_flag_not_part_of_external_configuration(tmp_path):
    with pytest.raises(TypeError):
        mod.VendorContainerDesign(network_enabled=True)


def test_wrong_git_source_blocks_argv_compilation(tmp_path, monkeypatch):
    x = design(tmp_path)
    def wrong(root, engine):
        item = proof(root, engine)
        item["gitlink_commit"] = "0" * 40
        return item
    monkeypatch.setattr(mod, "attest_pinned_vendor_checkout", wrong)
    with pytest.raises(ValueError, match="not pinned"):
        mod.compile_vendor_container_design(x)


def test_symlinked_or_nested_output_cannot_be_mounted(tmp_path):
    repo, inp, out = roots(tmp_path)
    alias = tmp_path / "alias_output"
    try:
        alias.symlink_to(out, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink unavailable")
    with pytest.raises(ValueError, match="Symlinked"):
        mod.VendorContainerDesign(
            engine="lean",
            image_by_digest="local/nrfx-lean@sha256:" + "4" * 64,
            frozen_parent_commit="a" * 40,
            frozen_request_sha256="b" * 64,
            repository_root=repo, input_root=inp, output_root=alias)


def test_parent_repository_cannot_be_writable_output_mount(tmp_path):
    repo, inp, out = roots(tmp_path)
    with pytest.raises(ValueError, match="must not overlap"):
        mod.VendorContainerDesign(
            engine="lean",
            image_by_digest="local/nrfx-lean@sha256:" + "4" * 64,
            frozen_parent_commit="a" * 40,
            frozen_request_sha256="b" * 64,
            repository_root=repo, input_root=inp,
            output_root=repo / "vendor/upstream/lean")


def test_bounded_resource_caps_are_not_boolean(tmp_path):
    with pytest.raises(ValueError, match="resource/identity"):
        design(tmp_path, cpu_count=True)
    with pytest.raises(ValueError, match="resource/identity"):
        # Recreate separate base paths because the helper must make new dirs.
        mod.VendorContainerDesign(
            engine="lean", image_by_digest="local/nrfx-lean@sha256:" + "4" * 64,
            frozen_parent_commit="a" * 40, frozen_request_sha256="b" * 64,
            repository_root=tmp_path / "none",
            input_root=tmp_path / "none", output_root=tmp_path / "none",
            memory_mib=1024 * 1024)


def test_no_image_or_container_process_is_started(tmp_path, monkeypatch):
    x = design(tmp_path)
    monkeypatch.setattr(mod, "attest_pinned_vendor_checkout", proof)
    # Only an argv vector is returned; Docker/Python subprocess are never called.
    artifact = mod.compile_vendor_container_design(x)
    assert artifact["engine_construction_only"] is True
    assert artifact["image_verified_locally"] is False
    assert artifact["market_data_opened"] is False


def test_real_synthetic_gitlink_compiles_then_local_source_tamper_blocks(
    tmp_path, monkeypatch,
):
    import subprocess
    from norisk_quant import vendor_checkout_attestation as attest

    def git(root, *args):
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, check=True)
        return result.stdout.strip()

    origin = tmp_path / "synthetic_vendor_origin"
    origin.mkdir()
    git(origin, "init", "-q")
    git(origin, "config", "user.email", "ci@example.invalid")
    git(origin, "config", "user.name", "Synthetic CI")
    source_files = (
        "Engine/DataFeeds/SubscriptionSynchronizer.cs",
        "Engine/Results/BacktestingResultHandler.cs",
    )
    for path in source_files:
        entry = origin / path
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text("// Synthetic Git source: no vendor executable\n")
    git(origin, "add", ".")
    git(origin, "commit", "-qm", "Frozen synthetic source")
    vendor_sha = git(origin, "rev-parse", "HEAD")

    host = tmp_path / "synthetic_host"
    host.mkdir()
    git(host, "init", "-q")
    git(host, "config", "user.email", "ci@example.invalid")
    git(host, "config", "user.name", "Synthetic CI")
    submodule = host / "vendor/upstream/lean"
    submodule.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(submodule)], check=True)
    git(host, "update-index", "--add", "--cacheinfo",
        f"160000,{vendor_sha},vendor/upstream/lean")
    git(host, "commit", "-qm", "Attach synthetic exact Git submodule")
    frozen_head = git(host, "rev-parse", "HEAD")
    synthetic_input = tmp_path / "synthetic_quote_manifest"
    private_output = tmp_path / "private_output"
    synthetic_input.mkdir()
    private_output.mkdir()

    # Patch only the EXPECTED upstream hash for this synthetic fake vendor.
    # The proof itself invokes real local Git and reads tracked bytes.
    monkeypatch.setitem(PINNED_VENDOR, "lean", vendor_sha)
    plan = mod.VendorContainerDesign(
        engine="lean",
        image_by_digest="local/nrfx-synthetic-lean@sha256:" + "a" * 64,
        frozen_parent_commit=frozen_head,
        frozen_request_sha256="b" * 64,
        repository_root=host,
        input_root=synthetic_input,
        output_root=private_output,
    )
    result = mod.compile_vendor_container_design(plan)
    assert result["source_gitlink_commit"] == vendor_sha
    assert result["vendor_started"] is False
    assert result["network_enabled"] is False

    # Even a legitimate local edit invalidates the pinned checkout.
    (submodule / source_files[0]).write_text(
        "// Unauthorized change after frozen source commit\n")
    with pytest.raises(ValueError):
        mod.compile_vendor_container_design(plan)
