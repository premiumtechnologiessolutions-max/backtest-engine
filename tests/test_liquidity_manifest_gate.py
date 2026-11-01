"""Contract tests for prospective registration structural gate."""
import copy
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_liquidity_manifest.py"
spec = importlib.util.spec_from_file_location("liquidity_manifest_gate", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def valid():
    d = {key: "fixed-before-oos" for key in module.REQUIRED}
    d.update(
        experiment_id="liquidity-sweep-v1",
        registered_at_utc="2026-11-01T12:00:00Z",
        oos_start_utc="2026-11-02T00:00:00Z",
        oos_end_utc="2027-02-01T00:00:00Z",
        engine_commit_sha="a" * 40,
        source_sha256="b" * 64,
        m1_bid_ask_fingerprint_sha256="c" * 64,
        dependencies_lock_sha256="d" * 64,
        timezone="UTC",
        contract_size_oz=100,
        all_in_cost_per_oz=0.40,
        max_holding_minutes=90,
        max_concurrent_positions=1,
        minimum_trades=100,
        minimum_active_months=3,
        max_drawdown_oz_usd=100.0,
        primary_pass_threshold=0.0,
        hypotheses_count=1,
    )
    return d

def test_valid_structure():
    assert module.validate(valid()) is True

@pytest.mark.parametrize("field,value", [
    ("all_in_cost_per_oz", 0.400001),
    ("all_in_cost_per_oz", True),
    ("registered_at_utc", "2026-11-02T00:00:00Z"),
    ("oos_start_utc", "2026-11-01T00:00:00Z"),
    ("oos_end_utc", "2026-11-02T00:00:00Z"),
    ("oos_start_utc", "2026-11-02T00:00:00"),
    ("timezone", "Asia/Beirut"),
    ("minimum_trades", 0),
    ("hypotheses_count", 1.5),
    ("max_drawdown_oz_usd", float("nan")),
    ("source_sha256", "not-a-sha"),
    ("engine_commit_sha", "a" * 7),
    ("entry_rule", ""),
])
def test_reject_invalid(field, value):
    data = valid()
    data[field] = value
    with pytest.raises(ValueError):
        module.validate(data)

def test_reject_missing_and_unknown_shape():
    data = valid()
    del data["stop_rule"]
    with pytest.raises(ValueError, match="missing required"):
        module.validate(data)
    with pytest.raises(ValueError):
        module.validate([])


@pytest.mark.parametrize("raw", [
    '{"experiment_id":"first","experiment_id":"overwritten"}',
    '{"outer":{"x":1,"x":2}}',
    '{"hypotheses_count":NaN}',
    '{"hypotheses_count":Infinity}',
    '{"hypotheses_count":-Infinity}',
])
def test_parse_rejects_ambiguous_or_nonfinite_json(raw):
    with pytest.raises(ValueError):
        module.parse_manifest(raw)


def test_parse_accepts_unambiguous_json():
    assert module.parse_manifest('{"experiment_id":"liquidity-v1"}') == {
        "experiment_id": "liquidity-v1"
    }
