"""Mission control read-only synthetic snapshot, no actual backtests."""
import hashlib
import json

import pytest

from norisk_quant.campaign_sharding import freeze_sharded_campaign
from norisk_quant.construction_mission_control import construction_snapshot
from scripts.quant_construction_snapshot import main
from scripts.durable_research_state import DurableResearchState
from scripts.durable_backup_attestation import backup_durable_state
from scripts.research_job_queue import _canonical


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
            "id": "liquidity_sweep", "code_sha256": "c" * 64,
            "spec_sha256": "d" * 64}],
        "execution_engines": ["norisk_quant", "lean"],
        "ai_reviewers": ["rd_agent"],
        "resource_limits": {"max_workers": 1, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 360},
        "all_in_cost_usd_per_ounce": 0.40,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    })


def test_missing_db_is_not_reported_as_healthy():
    snap = construction_snapshot(design())
    assert snap["operational_health"]["status"] == "NOT_CONFIGURED"
    assert snap["engine_completely_built"] is False
    assert snap["design"]["strategies_designed"] == 1
    assert snap["design"]["reference_engines"][0]["runtime_integrated_and_verified"] is False


def test_invalid_db_is_failed_closed(tmp_path):
    snap = construction_snapshot(design(), database=tmp_path / "missing.sqlite3")
    assert snap["operational_health"]["status"] == "INVALID"
    assert snap["market_research_authorized"] is False


def test_existing_sqlite_is_observed_without_mutation(tmp_path):
    store = DurableResearchState(tmp_path / "state.sqlite3")
    before = store.operational_snapshot(now_ms=1000)
    snap = construction_snapshot(
        design(), database=store.database, now_ms=1000)
    assert snap["operational_health"]["status"] == "HEALTHY"
    assert snap["operational_health"]["total_jobs"] == 0
    assert snap["engineering_acceptance_passed"] is False
    assert store.operational_snapshot(now_ms=1000) == before


def test_cli_renders_small_json_and_rejects_duplicates(tmp_path, capsys):
    source = tmp_path / "blueprint.json"
    source.write_text(json.dumps(design()), encoding="utf-8")
    assert main(["--design", str(source)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "CONSTRUCTION_NOT_COMPLETE_NO_EXECUTION"
    assert output["design"]["source_commit"] == "a" * 40
    assert output["market_data_opened_by_this_call"] is False
    source.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        main(["--design", str(source)])


def test_cli_cannot_promote_forged_execution_flag(tmp_path):
    source = tmp_path / "blueprint.json"
    payload = design()
    payload["workers_started"] = True
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        main(["--design", str(source)])


def test_cli_fails_on_symlinked_design(tmp_path):
    source = tmp_path / "blueprint.json"
    source.write_text(json.dumps(design()), encoding="utf-8")
    linked = tmp_path / "linked.json"
    try:
        linked.symlink_to(source)
    except OSError:
        pytest.skip("Symlinks not supported")
    with pytest.raises(ValueError, match="Unsafe"):
        main(["--design", str(linked)])

def test_verified_backup_visible_without_resuming_tasks(tmp_path, capsys):
    store = DurableResearchState(tmp_path / 'control.sqlite3')
    root = tmp_path / 'private_backups'
    root.mkdir()
    backup_durable_state(store.database, root, 'synthetic_001', now_ms=1250)
    snap = construction_snapshot(design(), database=store.database,
                                 backup_snapshot_dir=root / 'synthetic_001',
                                 now_ms=1250)
    assert snap['backup_health']['status'] == 'VERIFIED_REVIEW_ONLY'
    assert snap['backup_health']['manifest_verified'] is True
    assert snap['backup_health']['automatic_resume'] is False
    assert snap['market_research_authorized'] is False
    source = tmp_path / 'design.json'
    source.write_text(json.dumps(design()), encoding='utf-8')
    assert main(['--design', str(source), '--backup-dir', str(root / 'synthetic_001')]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown['backup_health']['jobs_observed'] == 0

def test_modified_backup_is_invalid_in_readonly_snapshot(tmp_path):
    store = DurableResearchState(tmp_path / 'control.sqlite3')
    root = tmp_path / 'private_backups'
    root.mkdir()
    backup_durable_state(store.database, root, 'synthetic_002', now_ms=1250)
    with (root / 'synthetic_002' / 'state.sqlite3').open('ab') as target:
        target.write(b'tampered')
    state = construction_snapshot(design(), backup_snapshot_dir=root / 'synthetic_002')
    assert state['backup_health']['status'] == 'INVALID'
    assert state['backup_health']['manifest_verified'] is False
    assert state['engineering_acceptance_passed'] is False

def test_no_backup_is_never_implicitly_verified():
    assert construction_snapshot(design())['backup_health']['status'] == 'NOT_CONFIGURED'
