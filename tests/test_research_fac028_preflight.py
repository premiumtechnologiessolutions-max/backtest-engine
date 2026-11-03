"""Synthetic-only readiness checks; no Gold source, fills, or P/L."""
import pytest
from scripts.research_fac028_preflight import (
    EXECUTION_KEYS, audit_fac028,
)

FROZEN = "24 parameter specifications; $0.40/oz; stop-first; adverse gap-through; one shared position"


def test_unresolved_semantics_fail_closed():
    result = audit_fac028(FROZEN)
    assert result["status"] == "BLOCKED_UNRESOLVED_EXECUTION_SEMANTICS"
    assert set(result["missing"]) == set(EXECUTION_KEYS)
    assert result["original_source_replays"] == 0


def test_missing_safeguard_rejected():
    with pytest.raises(ValueError):
        audit_fac028(FROZEN.replace("stop-first", "target-first"))


def test_complete_contract_only_enters_review_not_execution():
    result = audit_fac028(FROZEN, execution_contract={k: "explicitly frozen" for k in EXECUTION_KEYS})
    assert result["missing"] == []
    assert result["status"] == "READY_FOR_INDEPENDENT_CONTRACT_REVIEW_NOT_EXECUTION"
    assert result["independent_hypotheses"] == 1


def test_empty_contract_value_remains_blocked():
    contract = {k: "defined" for k in EXECUTION_KEYS}
    contract["entry_bid_ask_rule"] = " "
    assert audit_fac028(FROZEN, execution_contract=contract)["missing"] == ["entry_bid_ask_rule"]


@pytest.mark.parametrize("placeholder", ["TBD", "todo", "N/A", "pending", "?", "unknown"])
def test_nonempty_placeholder_does_not_clear_execution_gate(placeholder):
    contract = {k: "explicitly frozen" for k in EXECUTION_KEYS}
    contract["signal_timestamp_rule"] = placeholder
    result = audit_fac028(FROZEN, execution_contract=contract)
    assert result["status"] == "BLOCKED_UNRESOLVED_EXECUTION_SEMANTICS"
    assert result["missing"] == ["signal_timestamp_rule"]
