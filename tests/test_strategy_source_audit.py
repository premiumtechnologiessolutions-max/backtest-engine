"""Source hash checks on tiny synthetic strategy files only."""
import hashlib

import pytest

from norisk_quant.campaign_sharding import freeze_sharded_campaign
from norisk_quant.strategy_source_audit import audit_campaign_sources


def scenario(tmp_path):
    root = tmp_path / "repo"
    code_file = root / "src/norisk_quant/sample_strategy.py"
    code_file.parent.mkdir(parents=True, exist_ok=True)
    code_file.write_text("def frozen_signal():\n    return None\n", encoding="utf-8")
    spec_file = root / "research/strategy.md"
    spec_file.parent.mkdir(parents=True, exist_ok=True)
    spec_file.write_text("# Inert synthetic strategy\n", encoding="utf-8")
    spec = {
        "source_commit": "a" * 40,
        "dataset": {
            "id": "xauusd_m1", "archive_sha256": "b" * 64,
            "start": "2024-01-01", "end": "2024-12-31",
            "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2024-01-01", "end": "2024-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [{
            "id": "sample_strategy",
            "code_sha256": hashlib.sha256(code_file.read_bytes()).hexdigest(),
            "spec_sha256": hashlib.sha256(spec_file.read_bytes()).hexdigest(),
        }],
        "execution_engines": ["norisk_quant"],
        "ai_reviewers": [],
        "resource_limits": {"max_workers": 1, "max_ram_mb": 2048,
                            "max_disk_mb": 1024, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.40,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    }
    mapped = {"sample_strategy": {
        "code_path": "src/norisk_quant/sample_strategy.py",
        "spec_path": "research/strategy.md"}}
    return root, code_file, spec_file, freeze_sharded_campaign(spec), mapped


def test_byte_hash_verified_without_importing_strategy(tmp_path):
    root, code_file, spec_file, design, paths = scenario(tmp_path)
    result = audit_campaign_sources(design, root, paths)
    assert result["strategy_sources_checked"] == 1
    assert result["local_code_and_specs_sha256_verified"] is True
    assert result["git_commit_ancestry_verified"] is False
    assert result["strategies_imported_or_executed"] is False
    assert result["original_market_archive_verified"] is False


def test_mutated_code_or_spec_fails_closed(tmp_path):
    root, code_file, spec_file, design, paths = scenario(tmp_path)
    code_file.write_text("def frozen_signal():\n    return True\n")
    with pytest.raises(ValueError, match="SHA256 differs"):
        audit_campaign_sources(design, root, paths)
    root, code_file, spec_file, design, paths = scenario(tmp_path)
    spec_file.write_text("# silent mutation")
    with pytest.raises(ValueError, match="SHA256 differs"):
        audit_campaign_sources(design, root, paths)


def test_source_path_escape_or_symlink_refused(tmp_path):
    root, code_file, spec_file, design, paths = scenario(tmp_path)
    paths["sample_strategy"]["code_path"] = "../../etc/passwd"
    with pytest.raises(ValueError):
        audit_campaign_sources(design, root, paths)
    root, code_file, spec_file, design, paths = scenario(tmp_path)
    link = root / "src/norisk_quant/link.py"
    try:
        link.symlink_to(code_file)
    except OSError:
        pytest.skip("Symlinks unavailable")
    paths["sample_strategy"]["code_path"] = "src/norisk_quant/link.py"
    with pytest.raises(ValueError, match="Symlinked"):
        audit_campaign_sources(design, root, paths)


def test_missing_candidate_or_extra_secret_mapping_refused(tmp_path):
    root, code_file, spec_file, design, paths = scenario(tmp_path)
    with pytest.raises(ValueError, match="Every frozen"):
        audit_campaign_sources(design, root, {})
    paths["api_key"] = {"code_path": "secret", "spec_path": "secret"}
    with pytest.raises(ValueError, match="Every frozen"):
        audit_campaign_sources(design, root, paths)


def test_syntax_error_is_not_accepted_by_source_digest(tmp_path):
    root, code_file, spec_file, design, paths = scenario(tmp_path)
    invalid = "def broken(:\n"
    code_file.write_text(invalid, encoding="utf-8")
    x = design["normalized_global_spec"]
    x["strategies"][0]["code_sha256"] = hashlib.sha256(invalid.encode()).hexdigest()
    updated = freeze_sharded_campaign(x)
    with pytest.raises(ValueError, match="syntactically valid"):
        audit_campaign_sources(updated, root, paths)
