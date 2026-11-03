"""Fail-closed FAC028 preregistration readiness audit; never executes trades."""
from __future__ import annotations

import argparse
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
                                "undefined", "to be defined", "not specified",
                                "placeholder", "?"})


def _is_defined(value: object) -> bool:
    return (isinstance(value, str) and bool(value.strip())
            and value.strip().casefold() not in PLACEHOLDER_VALUES)


def audit_fac028(text: str, *, execution_contract: dict | None = None) -> dict:
    if not isinstance(text, str) or any(s not in text for s in REQUIRED):
        raise ValueError("FAC028 frozen protocol missing required safeguards")
    missing = [key for key in EXECUTION_KEYS
               if not isinstance(execution_contract, dict)
               or not _is_defined(execution_contract.get(key))]
    return {"status": "BLOCKED_UNRESOLVED_EXECUTION_SEMANTICS" if missing
            else "READY_FOR_INDEPENDENT_CONTRACT_REVIEW_NOT_EXECUTION",
            "missing": missing, "grid_specs": 24,
            "independent_hypotheses": 1, "original_source_replays": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frozen_protocol", type=Path)
    args = parser.parse_args()
    result = audit_fac028(args.frozen_protocol.read_text(encoding="utf-8"))
    print(result)
    return 2 if result["missing"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
