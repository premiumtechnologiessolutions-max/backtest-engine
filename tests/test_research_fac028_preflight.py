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


def test_unexpected_execution_key_fails_closed():
    contract = distinct_contract()
    contract["undocumented_override"] = "force execution"
    with pytest.raises(ValueError, match="unexpected FAC028 execution keys"):
        audit_fac028(FROZEN, execution_contract=contract)


def test_two_copied_rules_block_only_affected_dimensions():
    contract = distinct_contract()
    contract["entry_bid_ask_rule"] = contract["position_exit_time_rule"]
    result = audit_fac028(FROZEN, execution_contract=contract)
    assert result["status"] == "BLOCKED_UNRESOLVED_EXECUTION_SEMANTICS"
    assert set(result["missing"]) == {"entry_bid_ask_rule", "position_exit_time_rule"}

@pytest.mark.parametrize("placeholder", [
    "TBD: define later", "TODO - confirm broker feed", "Pending (owner)",
    "not specified: waiting for data", "N/A — not decided",
    "unknown: execution clock", "placeholder: sample text",
])
def test_prefixed_placeholder_is_not_a_frozen_rule(placeholder):
    contract = distinct_contract()
    contract["signal_timestamp_rule"] = placeholder
    assert audit_fac028(FROZEN, execution_contract=contract)["missing"] == [
        "signal_timestamp_rule"
    ]


@pytest.mark.parametrize("bad", [
    "valid rule\ninjected second rule", "valid rule\tfake table",
    "x" * 4097,
])
def test_control_characters_and_unbounded_rules_fail_closed(bad):
    contract = distinct_contract()
    contract["entry_bid_ask_rule"] = bad
    assert audit_fac028(FROZEN, execution_contract=contract)["missing"] == [
        "entry_bid_ask_rule"
    ]


def test_placeholder_word_inside_actual_execution_rule_is_not_false_positive():
    contract = distinct_contract()
    contract["position_exit_time_rule"] = (
        "At UTC 22:00 exit any pending position at first available BID/ASK quote"
    )
    assert audit_fac028(FROZEN, execution_contract=contract)["missing"] == []


def test_cli_emits_strict_machine_readable_json_when_ready(tmp_path, monkeypatch, capsys):
    import json
    import sys
    from scripts.research_fac028_preflight import main
    protocol = tmp_path / "protocol.md"
    protocol.write_text(FROZEN, encoding="utf-8")
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(distinct_contract()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["fac028", str(protocol), "--execution-contract", str(contract)])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "READY_FOR_INDEPENDENT_CONTRACT_REVIEW_NOT_EXECUTION"
    assert result["original_source_replays"] == 0
    assert result["missing"] == []


def test_cli_emits_json_even_when_blocked(tmp_path, monkeypatch, capsys):
    import json
    import sys
    from scripts.research_fac028_preflight import main
    protocol = tmp_path / "protocol.md"
    protocol.write_text(FROZEN, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["fac028", str(protocol)])
    assert main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "BLOCKED_UNRESOLVED_EXECUTION_SEMANTICS"
    assert set(result["missing"]) == set(EXECUTION_KEYS)
    assert result["original_source_replays"] == 0


@pytest.mark.parametrize("bad", ["UTC\u200b close of bar", "UTC\u202eclose of bar", "UTC\ufeff close of bar"])
def test_invisible_unicode_format_controls_blocked(bad):
    contract = distinct_contract()
    contract["signal_timestamp_rule"] = bad
    assert audit_fac028(FROZEN, execution_contract=contract)["missing"] == ["signal_timestamp_rule"]


def test_unicode_normalized_and_whitespace_variant_duplicates_blocked():
    contract = distinct_contract()
    contract["signal_timestamp_rule"] = "At UTC  12:00 use prior bar"
    contract["breakout_price_comparator"] = "At UTC\u00a012:00  use prior bar"
    result = audit_fac028(FROZEN, execution_contract=contract)
    assert set(result["missing"]) == {"signal_timestamp_rule", "breakout_price_comparator"}


@pytest.mark.parametrize("placeholder", [
    "\uff34\uff22\uff24",  # NFKC full-width TBD
    "\uff34\uff22\uff24\uff1a define later",
    "\uff30\uff25\uff2e\uff24\uff29\uff2e\uff27\uff08owner\uff09",
    "TBD\u00a0:\u00a0waiting for data",
    "\uff2e\uff0f\uff21",  # full-width N/A
])
def test_unicode_compatibility_placeholders_fail_closed(placeholder):
    contract = distinct_contract()
    contract["signal_timestamp_rule"] = placeholder
    result = audit_fac028(FROZEN, execution_contract=contract)
    assert result["missing"] == ["signal_timestamp_rule"]
    assert result["status"] == "BLOCKED_UNRESOLVED_EXECUTION_SEMANTICS"


def test_unicode_normalization_does_not_reject_real_rule():
    contract = distinct_contract()
    contract["signal_timestamp_rule"] = (
        "\uff21t UTC 12:00 use prior completed M1 candle and only known BID/ASK"
    )
    assert audit_fac028(FROZEN, execution_contract=contract)["missing"] == []


@pytest.mark.parametrize("placeholder", [
    "TBD define later", "TODO confirm broker feed", "Pending owner",
    "unknown definition", "not specified waiting for data",
])
def test_unseparated_deferred_execution_rule_cannot_clear_review_gate(placeholder):
    contract = distinct_contract()
    contract["signal_timestamp_rule"] = placeholder
    result = audit_fac028(FROZEN, execution_contract=contract)
    assert result["status"] == "BLOCKED_UNRESOLVED_EXECUTION_SEMANTICS"
    assert result["missing"] == ["signal_timestamp_rule"]


def test_real_pending_order_and_known_future_unknown_not_rejected():
    contract = distinct_contract()
    contract["position_exit_time_rule"] = (
        "Cancel pending order at UTC 22:00; exit existing position at next BID"
    )
    contract["session_calendar_definition"] = (
        "Unknown future market events are excluded; use frozen UTC calendar"
    )
    assert audit_fac028(FROZEN, execution_contract=contract)["missing"] == []


def test_partial_contract_reports_both_missing_and_duplicate_dimensions():
    contract = distinct_contract()
    contract["entry_bid_ask_rule"] = contract["position_exit_time_rule"]
    contract["signal_timestamp_rule"] = "TBD"
    result = audit_fac028(FROZEN, execution_contract=contract)
    assert result["status"] == "BLOCKED_UNRESOLVED_EXECUTION_SEMANTICS"
    assert result["missing"] == [
        "signal_timestamp_rule", "position_exit_time_rule", "entry_bid_ask_rule"
    ]
    assert result["original_source_replays"] == 0
