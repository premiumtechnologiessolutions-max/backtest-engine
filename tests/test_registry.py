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
