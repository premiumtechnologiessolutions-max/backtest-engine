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


def test_cli_contract_json_review_only(tmp_path, monkeypatch, capsys):
    import json
    import sys
    from scripts.research_fac028_preflight import main
    protocol = tmp_path / "protocol.md"
    protocol.write_text(FROZEN, encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({k: "explicitly frozen" for k in EXECUTION_KEYS}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["fac028", str(protocol), "--execution-contract", str(contract)])
    assert main() == 0
    assert "READY_FOR_INDEPENDENT_CONTRACT_REVIEW_NOT_EXECUTION" in capsys.readouterr().out


def test_cli_rejects_json_array(tmp_path, monkeypatch):
    import sys
    from scripts.research_fac028_preflight import main
    protocol = tmp_path / "protocol.md"
    protocol.write_text(FROZEN, encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["fac028", str(protocol), "--execution-contract", str(contract)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
