"""FAC028 independent machine-readable contract shape gate (not strategy approval).

This gate deliberately does not infer execution semantics from prose or market
results. It only checks a tightly typed preregistration envelope. A PASS is
necessary but never sufficient for canonical parity or Gold M1 execution.
"""
from __future__ import annotations

import hashlib
import json

FIELDS = (
    "signal_timestamp_rule", "breakout_price_comparator",
    "session_calendar_definition", "daily_true_range_definition",
    "shock_reference_session", "position_arbitration_rule",
    "position_exit_time_rule", "entry_bid_ask_rule",
)
FORBIDDEN = {"tbd", "todo", "n/a", "unknown", "pending", "defined",
             "specified", "explicitly frozen", "yes", "ok", "?"}


def audit_contract(contract: object) -> dict:
    """Fail closed on missing fields, extra keys, and non-atomic semantics."""
    if type(contract) is not dict:
        raise ValueError("contract must be a JSON object")
    if set(contract) != set(FIELDS):
        raise ValueError("contract must have exactly the eight frozen keys")
    for key in FIELDS:
        value = contract[key]
        if type(value) is not str or not value.strip() or value != value.strip():
            raise ValueError(f"{key}: nonempty canonical string required")
        if len(value) > 2000 or value.casefold() in FORBIDDEN:
            raise ValueError(f"{key}: placeholder or excessive text")
        if any(ord(ch) < 32 for ch in value):
            raise ValueError(f"{key}: control character")
    frozen = json.dumps(contract, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":")).encode("utf-8")
    return {"status": "SHAPE_VALID_ONLY_NOT_EXECUTION_APPROVED",
            "fingerprint_sha256": hashlib.sha256(frozen).hexdigest(),
            "keys_checked": len(FIELDS), "gold_backtests": 0}


def main() -> int:
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_contract(json.loads(args.contract.read_text(encoding="utf-8"))),
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
