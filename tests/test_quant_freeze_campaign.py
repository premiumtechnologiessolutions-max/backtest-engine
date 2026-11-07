"""Construction CLI is safe/idempotent on entirely synthetic JSON specs."""
import json

import pytest

from scripts.quant_freeze_campaign import freeze_local_spec, main
from scripts.quant_construction_snapshot import main as status_main


def spec():
    return {
        "source_commit": "a" * 40,
        "dataset": {
            "id": "xauusd_m1", "archive_sha256": "b" * 64,
            "start": "2024-01-01", "end": "2024-12-31",
            "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2024-01-01", "end": "2024-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [{
            "id": "synthetic_strategy", "code_sha256": "c" * 64,
            "spec_sha256": "d" * 64}],
        "execution_engines": ["norisk_quant", "lean"],
        "ai_reviewers": ["rd_agent"],
        "resource_limits": {"max_workers": 1, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.4,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    }


def test_freeze_spec_to_dashboard_snapshot_workflow(tmp_path, capsys):
    input_path, output_path = tmp_path / "spec.json", tmp_path / "design.json"
    input_path.write_text(json.dumps(spec()), encoding="utf-8")
    first = freeze_local_spec(input_path, output_path)
    assert first["status"] == "FROZEN_CONSTRUCTION_DESIGN_ONLY"
    assert first["market_data_opened"] is False
    assert output_path.exists()
    original = output_path.read_bytes()
    repeated = freeze_local_spec(input_path, output_path)
    assert repeated["status"] == "ALREADY_FROZEN_IDENTICAL"
    assert output_path.read_bytes() == original
    assert status_main(["--design", str(output_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["design"]["strategies_designed"] == 1
    assert payload["engine_completely_built"] is False


def test_immutable_output_conflict_refused(tmp_path):
    input_path, output_path = tmp_path / "spec.json", tmp_path / "design.json"
    input_path.write_text(json.dumps(spec()), encoding="utf-8")
    freeze_local_spec(input_path, output_path)
    edited = spec()
    edited["resource_limits"]["max_workers"] = 2
    input_path.write_text(json.dumps(edited), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot be overwritten"):
        freeze_local_spec(input_path, output_path)


def test_duplicate_json_keys_cannot_change_frozen_intent(tmp_path):
    input_path, output_path = tmp_path / "spec.json", tmp_path / "design.json"
    input_path.write_text('{"x":1,"x":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        freeze_local_spec(input_path, output_path)
    assert not output_path.exists()


def test_unsanctioned_execution_flag_fails_before_output(tmp_path):
    input_path, output_path = tmp_path / "spec.json", tmp_path / "design.json"
    x = spec()
    x["execute"] = True
    input_path.write_text(json.dumps(x), encoding="utf-8")
    with pytest.raises(ValueError):
        freeze_local_spec(input_path, output_path)
    assert not output_path.exists()


def test_symlink_output_not_overwritten(tmp_path):
    input_path, output_path = tmp_path / "spec.json", tmp_path / "design.json"
    input_path.write_text(json.dumps(spec()), encoding="utf-8")
    other = tmp_path / "private.json"
    other.write_text("private", encoding="utf-8")
    try:
        output_path.symlink_to(other)
    except OSError:
        pytest.skip("Symlink not supported")
    with pytest.raises(ValueError, match="Unsafe"):
        freeze_local_spec(input_path, output_path)
    assert other.read_text(encoding="utf-8") == "private"
