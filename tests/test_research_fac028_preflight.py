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


def distinct_contract():
    return {key: f"Frozen UTC causal execution rule {index}: uses only completed prior bars" for index, key in enumerate(EXECUTION_KEYS)}


def test_identical_copy_paste_contract_is_blocked():
    contract = {key: "UTC close of prior completed H1 bar, deterministic" for key in EXECUTION_KEYS}
    result = audit_fac028(FROZEN, execution_contract=contract)
    assert result["status"] == "BLOCKED_UNRESOLVED_EXECUTION_SEMANTICS"
    assert set(result["missing"]) == set(EXECUTION_KEYS)


def test_complete_contract_only_enters_review_not_execution():
    result = audit_fac028(FROZEN, execution_contract=distinct_contract())
    assert result["missing"] == []
    assert result["status"] == "READY_FOR_INDEPENDENT_CONTRACT_REVIEW_NOT_EXECUTION"
    assert result["independent_hypotheses"] == 1


def test_empty_contract_value_remains_blocked():
    contract = distinct_contract()
    contract["entry_bid_ask_rule"] = " "
    assert audit_fac028(FROZEN, execution_contract=contract)["missing"] == ["entry_bid_ask_rule"]


@pytest.mark.parametrize("placeholder", ["TBD", "todo", "N/A", "pending", "?", "unknown"])
def test_nonempty_placeholder_does_not_clear_execution_gate(placeholder):
    contract = distinct_contract()
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
    contract.write_text(json.dumps(distinct_contract()), encoding="utf-8")
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


def test_generic_attestations_cannot_clear_review_gate():
    for generic in ("defined", "explicitly frozen", "specified", "yes", "ok"):
        contract = {key: "UTC close of prior completed H1 bar, deterministic" for key in EXECUTION_KEYS}
        contract["signal_timestamp_rule"] = generic
        result = audit_fac028(FROZEN, execution_contract=contract)
        assert result["status"] == "BLOCKED_UNRESOLVED_EXECUTION_SEMANTICS"
        assert result["missing"] == ["signal_timestamp_rule"]


@pytest.mark.parametrize("payload", [
    '{"signal_timestamp_rule":"a","signal_timestamp_rule":"b"}',
    '{"signal_timestamp_rule":NaN}',
    '{"signal_timestamp_rule":Infinity}',
])
def test_cli_rejects_ambiguous_or_nonfinite_json(tmp_path, monkeypatch, payload):
    import sys
    from scripts.research_fac028_preflight import main
    protocol = tmp_path / "protocol.md"
    protocol.write_text(FROZEN, encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["fac028", str(protocol), "--execution-contract", str(contract)])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
