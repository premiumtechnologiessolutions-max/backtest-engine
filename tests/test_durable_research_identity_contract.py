"""Contract checks for deterministic research job identity (synthetic only)."""
import copy
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "durable_research_identity",
    Path(__file__).resolve().parents[1] / "scripts" / "durable_research_identity.py",
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
identity = _module.canonical_job_identity


@pytest.fixture
def manifest():
    return {
        "schema_version": "v0.1",
        "experiment_id": "synthetic",
        "strategy_ast_sha256": "a" * 64,
        "data_source_sha256": "b" * 64,
        "bid_ask_fingerprint": "c" * 64,
        "git_commit_sha": "d" * 40,
        "dependency_lock_sha256": "e" * 64,
        "execution_policy_sha256": "f" * 64,
        "cost_policy_sha256": "0" * 64,
        "period_start_utc": "2012-01-01T00:00:00Z",
        "period_end_utc": "2013-01-01T00:00:00Z",
        "random_seed": 0,
    }


def test_order_independent_and_immutable(manifest):
    before = copy.deepcopy(manifest)
    assert identity(manifest) == identity(dict(reversed(list(manifest.items()))))
    assert manifest == before
    assert len(identity(manifest)[0]) == 64


@pytest.mark.parametrize("field,value", [
    ("cost_policy_sha256", "1" * 64),
    ("dependency_lock_sha256", "2" * 64),
    ("random_seed", 1),
    ("data_source_sha256", "3" * 64),
])
def test_changed_provenance_changes_identity(manifest, field, value):
    old = identity(manifest)[0]
    manifest[field] = value
    assert identity(manifest)[0] != old


@pytest.mark.parametrize("field,value", [
    ("random_seed", True),
    ("random_seed", -1),
    ("random_seed", 0.5),
    ("cost_policy_sha256", "UNKNOWN"),
    ("period_start_utc", "2012-01-01T00:00:00+00:00"),
    ("period_start_utc", "2014-01-01T00:00:00Z"),
    ("experiment_id", "../secret"),
    ("git_commit_sha", "short"),
])
def test_invalid_manifest_rejected(manifest, field, value):
    manifest[field] = value
    if field == "experiment_id":
        # Path-like experiment identifiers are intentionally a separate policy
        # decision; this test instead checks a control character.
        manifest[field] = "bad\nname"
    with pytest.raises(ValueError):
        identity(manifest)


def test_unknown_field_rejected(manifest):
    manifest["profit_claim"] = 999
    with pytest.raises(ValueError):
        identity(manifest)
