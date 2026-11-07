"""Synthetic-only fingerprint contract tests; no market or worker access."""
import pytest
from scripts.construction_job_fingerprint import fingerprint


def spec():
    return {"kind": "synthetic_unit_test", "name": "synthetic_contract",
            "source_commit": "a" * 40,
            "fixture": "tests/fixtures/synthetic/contract_1.json"}


def test_order_independent_and_inert():
    request = spec()
    a = fingerprint(request)
    b = fingerprint(dict(reversed(list(request.items()))))
    assert a == b
    assert len(a["job_fingerprint"]) == 64
    assert a["status"] == "INERT_NOT_QUEUED"
    assert a["execution_started"] is False
    assert a["market_data_accessed"] is False


@pytest.mark.parametrize("field,value", [
    ("name", "another_contract"),
    ("source_commit", "b" * 40),
    ("fixture", "tests/fixtures/synthetic/contract_2.json"),
    ("kind", "synthetic_contract_test"),
])
def test_material_changes_change_identity(field, value):
    request = spec()
    request[field] = value
    assert fingerprint(request)["job_fingerprint"] != fingerprint(spec())["job_fingerprint"]


@pytest.mark.parametrize("field,value", [
    ("kind", "backtest"), ("kind", "live_trade"),
    ("fixture", "../Gold data.zip"), ("name", "unsafe; echo hi"),
])
def test_reject_unsafe_request(field, value):
    request = spec()
    request[field] = value
    with pytest.raises(ValueError):
        fingerprint(request)


def test_reject_extra_execution_payload():
    request = spec()
    request["command"] = "python worker.py"
    with pytest.raises(ValueError):
        fingerprint(request)
