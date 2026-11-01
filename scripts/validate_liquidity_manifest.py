"""Fail-closed prospective liquidity experiment registration gate.

Usage: python scripts/validate_liquidity_manifest.py path/to/manifest.json
This tool validates registration structure only; it does NOT establish that a
manifest was committed before OOS data was viewed or that a strategy is sound.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

REQUIRED = {
    "experiment_id", "hypothesis_family", "registered_at_utc",
    "engine_commit_sha", "source_id", "source_sha256",
    "m1_bid_ask_fingerprint_sha256", "dependencies_lock_sha256",
    "timezone", "contract_size_oz", "all_in_cost_per_oz",
    "session_boundary", "lookback", "gap_policy", "sweep_threshold",
    "reclaim_confirmation", "entry_rule", "order_expiry",
    "stop_rule", "target_rule", "max_holding_minutes",
    "max_concurrent_positions", "end_window_exit",
    "training_selection_method", "oos_start_utc", "oos_end_utc",
    "minimum_trades", "minimum_active_months", "max_drawdown_oz_usd",
    "primary_statistic", "primary_pass_threshold",
    "hypotheses_count", "multiple_testing_method", "family_abort_rule",
}

def _utc(value, name):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO8601 UTC timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise ValueError(f"{name} must be UTC aware")
    return parsed

def _sha(value, name):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name} must be lowercase SHA256")

def validate(data):
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    missing = sorted(REQUIRED - data.keys())
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))
    for key in REQUIRED - {"contract_size_oz", "all_in_cost_per_oz", "max_holding_minutes",
                           "max_concurrent_positions", "minimum_trades", "minimum_active_months",
                           "max_drawdown_oz_usd", "primary_pass_threshold", "hypotheses_count"}:
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(f"{key} must be a nonempty string")
    for key in ("source_sha256", "m1_bid_ask_fingerprint_sha256", "dependencies_lock_sha256"):
        _sha(data[key], key)
    commit = data["engine_commit_sha"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise ValueError("engine_commit_sha must be a full lowercase Git SHA1")
    registered = _utc(data["registered_at_utc"], "registered_at_utc")
    start = _utc(data["oos_start_utc"], "oos_start_utc")
    end = _utc(data["oos_end_utc"], "oos_end_utc")
    if start < dt.datetime(2026, 11, 2, tzinfo=dt.timezone.utc):
        raise ValueError("OOS begins before prospective cutoff")
    if not (registered < start < end):
        raise ValueError("registration must precede OOS start, which must precede end")
    if data["timezone"] != "UTC":
        raise ValueError("timezone must be UTC")
    if type(data["all_in_cost_per_oz"]) not in (int, float) or data["all_in_cost_per_oz"] != 0.40:
        raise ValueError("canonical all-in cost must be exactly 0.40 USD/oz")
    for key in ("contract_size_oz", "max_holding_minutes", "max_concurrent_positions",
                "minimum_trades", "minimum_active_months", "hypotheses_count"):
        v = data[key]
        if type(v) not in (int, float) or not math.isfinite(v) or v <= 0:
            raise ValueError(f"{key} must be positive and finite")
        if key != "contract_size_oz" and (type(v) is not int):
            raise ValueError(f"{key} must be an integer")
    for key in ("max_drawdown_oz_usd", "primary_pass_threshold"):
        v = data[key]
        if type(v) not in (int, float) or not math.isfinite(v):
            raise ValueError(f"{key} must be finite")
    if data["max_drawdown_oz_usd"] <= 0:
        raise ValueError("max_drawdown_oz_usd must be positive")
    return True

def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"non-finite JSON numeric literal: {value}")


def parse_manifest(raw):
    """Reject duplicate keys and NaN/Infinity before validating registration."""
    return json.loads(raw, object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    data = parse_manifest(raw)
    validate(data)
    print(json.dumps({"status": "STRUCTURE_VALID_ONLY",
                      "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                      "experiment_id": data["experiment_id"]}, sort_keys=True))

if __name__ == "__main__":
    main()
