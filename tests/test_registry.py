import pytest

from norisk_quant.registry import (
    ExperimentIdentity, experiment_manifest, fingerprint,
)


def identity(**updates):
    params = {
        "dataset_sha256": "a" * 64,
        "engine_commit": "b" * 40,
        "strategy_id": "fvg_h1_retest",
        "parameters": {"atr_stop": 1.5, "rr": 2},
        "timeframe": "H1",
        "window_start_utc": "2012-01-01T00:00:00+00:00",
        "window_end_exclusive_utc": "2019-01-01T00:00:00+00:00",
        "quantity_ounces": 1.0,
    }
    params.update(updates)
    return ExperimentIdentity(**params)


def test_same_inputs_same_research_id():
    a = identity(parameters={"rr": 2, "atr_stop": 1.5})
    b = identity(parameters={"atr_stop": 1.5, "rr": 2})
    assert fingerprint(a) == fingerprint(b)
    assert experiment_manifest(a)["execution_status"] == "DEFINED_ONLY"
    assert experiment_manifest(a)["independent_test_proven"] is False


def test_source_code_or_all_in_fee_change_changes_fingerprint():
    base = identity()
    assert fingerprint(base) != fingerprint(identity(dataset_sha256="f" * 64))
    assert fingerprint(base) != fingerprint(identity(engine_commit="e" * 40))
    assert fingerprint(base) != fingerprint(identity(fee_all_in_per_ounce=0.45))


def test_invalid_data_provenance_and_tick_execution_rejected():
    with pytest.raises(ValueError, match="SHA-256"):
        identity(dataset_sha256="short")
    with pytest.raises(ValueError, match="full 40"):
        identity(engine_commit="main")
    with pytest.raises(ValueError, match="not implemented"):
        identity(execution_mode="observed_tick_research")


def test_frozen_identity_rejects_nested_parameter_mutation():
    params = {"rr": 2, "nested": {"window": [3, 5]}}
    item = identity(parameters=params)
    original = fingerprint(item)
    params["nested"]["window"].append(8)
    with pytest.raises(ValueError, match="mutated"):
        fingerprint(item)
    with pytest.raises(ValueError, match="mutated"):
        experiment_manifest(item)
    assert original != ""


def test_invalid_parameter_json_and_nonfinite_fee_rejected():
    for params in ({"rr": float("nan")}, {"rr": complex(1, 2)}, {"rr": {1, 2}}):
        with pytest.raises(ValueError, match="finite JSON"):
            identity(parameters=params)
    with pytest.raises(ValueError, match="Nonfinite"):
        identity(fee_all_in_per_ounce=float("inf"))


def test_equivalent_numeric_parameter_inputs_share_frozen_identity():
    assert fingerprint(identity(parameters={"stop_usd": 8})) == fingerprint(
        identity(parameters={"stop_usd": 8.0}))


def test_external_mutation_rejected_before_manifest_or_hash_changes():
    original = {"risk": {"legs": [1, 2]}}
    frozen = identity(parameters=original)
    frozen_id = fingerprint(frozen)
    original["risk"]["legs"].append(3)
    with pytest.raises(ValueError, match="mutated"):
        fingerprint(frozen)
    with pytest.raises(ValueError, match="mutated"):
        experiment_manifest(frozen)
    assert frozen_id != ""
