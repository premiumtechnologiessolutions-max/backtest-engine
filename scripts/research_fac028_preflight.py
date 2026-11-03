"""Fail-closed FAC028 preregistration readiness audit; never executes trades."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REQUIRED = (
    "24 parameter specifications",
    "$0.40/oz",
    "stop-first",
    "adverse gap-through",
    "one shared position",
)
# These details cannot be inferred from observed outcomes after a freeze.
EXECUTION_KEYS = (
    "signal_timestamp_rule",
    "breakout_price_comparator",
    "session_calendar_definition",
    "daily_true_range_definition",
    "shock_reference_session",
    "position_arbitration_rule",
    "position_exit_time_rule",
    "entry_bid_ask_rule",
)


# A nonempty placeholder is not an executable, frozen definition.
PLACEHOLDER_VALUES = frozenset({"tbd", "todo", "unknown", "n/a", "na", "pending",
                                "defined", "explicitly frozen", "specified", "yes", "ok",
                                "undefined", "to be defined", "not specified",
                                "placeholder", "?"})


# A rule may be nonempty but still explicitly defer its definition.
# Only reject leading placeholder labels, not substantive references to
# a pending order or unknown future market event.
_PLACEHOLDER_PREFIX = re.compile(
    r"^(?:tbd|todo|to\s+be\s+defined|not\s+specified|"
    r"unknown|undefined|pending|n/?a|placeholder)\s*(?::|[-–—]|\(|$)",
    flags=re.IGNORECASE,
)
MAX_RULE_CHARS = 4096


def _is_defined(value: object) -> bool:
    if not isinstance(value, str):
        return False
    rule = value.strip()
    if not rule or len(rule) > MAX_RULE_CHARS:
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in rule):
        return False
    return (rule.casefold() not in PLACEHOLDER_VALUES
            and _PLACEHOLDER_PREFIX.match(rule) is None)


def audit_fac028(text: str, *, execution_contract: dict | None = None) -> dict:
    if not isinstance(text, str) or any(s not in text for s in REQUIRED):
        raise ValueError("FAC028 frozen protocol missing required safeguards")
    if isinstance(execution_contract, dict):
        unexpected = sorted(set(execution_contract) - set(EXECUTION_KEYS))
        if unexpected:
            raise ValueError(f"unexpected FAC028 execution keys: {unexpected}")
    missing = [key for key in EXECUTION_KEYS
               if not isinstance(execution_contract, dict)
               or not _is_defined(execution_contract.get(key))]
    # Repeating one generic sentence for unrelated semantics is not a contract.
    if isinstance(execution_contract, dict) and not missing:
        values = [execution_contract[key].strip().casefold() for key in EXECUTION_KEYS]
        if len(set(values)) != len(values):
            # Any copied semantics across distinct execution dimensions need review.
            duplicates = {value for value in values if values.count(value) > 1}
            missing = [key for key, value in zip(EXECUTION_KEYS, values)
                       if value in duplicates]
    return {"status": "BLOCKED_UNRESOLVED_EXECUTION_SEMANTICS" if missing
            else "READY_FOR_INDEPENDENT_CONTRACT_REVIEW_NOT_EXECUTION",
            "missing": missing, "grid_specs": 24,
            "independent_hypotheses": 1, "original_source_replays": 0}


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate execution contract key: {key}")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen_protocol", type=Path)
    parser.add_argument("--execution-contract", type=Path, help="Local JSON object of frozen execution semantics")
    args = parser.parse_args()
    contract = None
    if args.execution_contract is not None:
        try:
            contract = json.loads(args.execution_contract.read_text(encoding="utf-8"),
                                  object_pairs_hook=_reject_duplicate_keys,
                                  parse_constant=lambda value: (_ for _ in ()).throw(
                                      ValueError(f"non-finite JSON constant: {value}")))
        except (OSError, ValueError) as exc:
            parser.error(f"invalid execution contract: {exc}")
        if not isinstance(contract, dict):
            parser.error("execution contract must be a JSON object")
    result = audit_fac028(args.frozen_protocol.read_text(encoding="utf-8"), execution_contract=contract)
    print(result)
    return 2 if result["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
