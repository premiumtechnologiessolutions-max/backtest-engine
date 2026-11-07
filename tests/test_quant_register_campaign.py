"""End-to-end CONSTRUCTION-ONLY freeze → SQLite DAG → dashboard snapshot."""
import json

import pytest

from scripts.quant_freeze_campaign import freeze_local_spec
from scripts.quant_register_campaign import main as registry_main
from scripts.quant_construction_snapshot import main as snapshot_main


def spec():
    return {
        "source_commit": "a" * 40,
        "dataset": {"id": "xauusd_m1", "archive_sha256": "b" * 64,
                    "start": "2024-01-01", "end": "2024-12-31",
                    "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2024-01-01", "end": "2024-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [
            {"id": "bos_fib", "code_sha256": "c" * 64,
             "spec_sha256": "d" * 64},
            {"id": "liquidity_sweep", "code_sha256": "e" * 64,
             "spec_sha256": "f" * 64}
        ],
        "execution_engines": ["norisk_quant", "nautilus"],
        "ai_reviewers": ["rd_agent"],
        "resource_limits": {"max_workers": 2, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.40,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    }


def test_full_offline_construction_pipeline_without_research(tmp_path, capsys):
    source = tmp_path / "spec.json"
    designed = tmp_path / "frozen_design.json"
    db = tmp_path / "state.sqlite3"
    source.write_text(json.dumps(spec()), encoding="utf-8")
    frozen = freeze_local_spec(source, designed)
    assert frozen["market_data_opened"] is False
    assert registry_main(["register", "--design", str(designed),
                          "--database", str(db)]) == 0
    added = json.loads(capsys.readouterr().out)
    assert added["registration_status"] == "REGISTERED_INERT"
    assert added["worker_started"] is False
    assert registry_main(["register", "--design", str(designed),
                          "--database", str(db)]) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["registration_status"] == "ALREADY_REGISTERED_IDENTICAL"
    assert registry_main(["audit", "--database", str(db)]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["registry"]["campaign_count"] == 1
    assert checked["registry"]["execution_enabled"] is False
    assert snapshot_main(["--design", str(designed),
                          "--database", str(db)]) == 0
    displayed = json.loads(capsys.readouterr().out)
    assert displayed["operational_health"]["construction_campaigns"] == 1
    assert displayed["operational_health"]["registered_dag_nodes"] == frozen["nodes"]
    assert displayed["market_research_authorized"] is False
    assert displayed["engineering_acceptance_passed"] is False


def test_inspecting_missing_database_never_creates_one(tmp_path):
    missing = tmp_path / "never_create.sqlite3"
    with pytest.raises(ValueError, match="missing or invalid"):
        registry_main(["audit", "--database", str(missing)])
    assert not missing.exists()


def test_public_execution_authority_is_denied_before_registration(tmp_path):
    source = tmp_path / "unsafe.json"
    designed = tmp_path / "unfrozen_design.json"
    spec_with_run = spec()
    spec_with_run["execute"] = True
    source.write_text(json.dumps(spec_with_run), encoding="utf-8")
    with pytest.raises(ValueError):
        freeze_local_spec(source, designed)
    assert not designed.exists()
