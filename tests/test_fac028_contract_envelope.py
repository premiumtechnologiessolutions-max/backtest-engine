"""FAC028 preregistration envelope tests; no price data or live trading."""
import pytest
from scripts.fac028_contract_envelope import FIELDS, audit_contract


def valid():
    return {k: f"precommitted deterministic rule for {k}" for k in FIELDS}


def test_valid_shape_is_not_execution_approval():
    result = audit_contract(valid())
    assert result["status"] == "SHAPE_VALID_ONLY_NOT_EXECUTION_APPROVED"
    assert result["keys_checked"] == 8
    assert result["gold_backtests"] == 0
    assert len(result["fingerprint_sha256"]) == 64


@pytest.mark.parametrize("value", ["TBD", "defined", "", None, True, "x\ncommand"])
def test_reject_unusable_rule(value):
    data = valid()
    data[FIELDS[0]] = value
    with pytest.raises(ValueError):
        audit_contract(data)


def test_reject_extra_and_missing_keys():
    data = valid()
    data["unfrozen_extra"] = "x"
    with pytest.raises(ValueError):
        audit_contract(data)
    del data["unfrozen_extra"]
    del data[FIELDS[1]]
    with pytest.raises(ValueError):
        audit_contract(data)


def test_fingerprint_is_order_independent_but_content_sensitive():
    data = valid()
    digest = audit_contract(data)["fingerprint_sha256"]
    assert audit_contract(dict(reversed(list(data.items()))))["fingerprint_sha256"] == digest
    data[FIELDS[2]] += " revised"
    assert audit_contract(data)["fingerprint_sha256"] != digest
