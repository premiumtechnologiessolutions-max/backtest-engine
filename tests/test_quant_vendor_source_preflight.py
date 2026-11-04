"""Inert preflight checks frozen campaign and every planned vendor pin."""
import json

import pytest

from norisk_quant.campaign_sharding import freeze_sharded_campaign
from scripts import quant_vendor_source_preflight as preflight


def design():
    return freeze_sharded_campaign({
        "source_commit": "a" * 40,
        "dataset": {
            "id": "xauusd_m1", "archive_sha256": "b" * 64,
            "start": "2024-01-01", "end": "2024-12-31",
            "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2024-01-01", "end": "2024-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [{
            "id": "bos_fib", "code_sha256": "c" * 64,
            "spec_sha256": "d" * 64}],
        "execution_engines": ["norisk_quant", "lean", "nautilus"],
        "ai_reviewers": [],
        "resource_limits": {"max_workers": 2, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.4,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    })


def mock_source(engine, parent="a" * 40):
    return {
        "parent_commit": parent,
        "gitlink_commit": "c" * 40 if engine == "lean" else "d" * 40,
        "selected_entrypoints": [{"path": "source.py",
                                  "source_sha256": "e" * 64}],
    }


def test_two_vendor_engines_must_both_match_frozen_commit(tmp_path, monkeypatch):
    seen = []
    def checker(root, engine):
        seen.append(engine)
        return mock_source(engine)
    monkeypatch.setattr(preflight, "attest_pinned_vendor_checkout", checker)
    result = preflight.preflight_vendor_sources(design(), tmp_path)
    assert result["source_check_status"] == "ALL_LOCAL_SOURCE_PINS_VERIFIED_NOT_RUN"
    assert result["blocked_engines"] == []
    assert seen == ["lean", "nautilus"]
    assert result["engineering_acceptance_passed"] is False
    assert result["external_vendor_started"] is False


def test_wrong_parent_commit_blocks_individual_engine(tmp_path, monkeypatch):
    def checker(root, engine):
        return mock_source(engine, parent="0" * 40 if engine == "lean" else "a" * 40)
    monkeypatch.setattr(preflight, "attest_pinned_vendor_checkout", checker)
    result = preflight.preflight_vendor_sources(design(), tmp_path)
    assert result["blocked_engines"] == ["lean"]
    assert len(result["source_verified"]) == 1


def test_missing_materialized_checkouts_fail_closed(tmp_path):
    result = preflight.preflight_vendor_sources(design(), tmp_path)
    assert set(result["blocked_engines"]) == {"lean", "nautilus"}
    assert result["source_check_status"] == "BLOCKED_VENDOR_SOURCE_NOT_ATTESTED"


def test_tampered_frozen_blueprint_never_preflights(tmp_path):
    value = design()
    value["frozen_shards"][0]["blueprint"]["dag"][0]["execution_enabled"] = True
    with pytest.raises(ValueError):
        preflight.preflight_vendor_sources(value, tmp_path)


def test_cli_returns_blocked_without_opening_market_data(tmp_path, capsys):
    source = tmp_path / "design.json"
    source.write_text(json.dumps(design()), encoding="utf-8")
    assert preflight.main(["--design", str(source), "--checkout", str(tmp_path)]) == 2
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["market_data_accessed"] is False
    assert parsed["independent_runner_attested"] is False
