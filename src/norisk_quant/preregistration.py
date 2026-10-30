"""Fail-closed preregistration for future XAUUSD hypothesis evaluation.

This module prevents accidental reuse of exposed historical periods as
"prospective" validation. A local timestamp is NOT independent proof of
preregistration: archive the manifest in a dated external Git commit before
collecting any holdout quotes. No broker execution or trading integration.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import math
import re

SCHEMA = "NRFX_PROSPECTIVE_STUDY_V1"
_KEYS = frozenset({
    "schema", "strategy", "strategy_blob_sha", "training_archive_sha256",
    "registered_at_utc", "known_exposed_through", "train_end",
    "holdout_start", "holdout_end", "fee_usd_per_oz", "parameters",
    "evidence_status",
})
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA64 = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[a-z][a-z0-9_-]{2,79}\Z")


def _day(value: object, label: str) -> date:
    if type(value) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{label} must be an ISO calendar date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} is not a valid date") from exc


def _registered(value: object) -> datetime:
    if type(value) is not str or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise ValueError("registered_at_utc requires explicit seconds and UTC Z")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid UTC registration timestamp") from exc


def _parameters(value: object) -> None:
    if type(value) is not dict or not value:
        raise ValueError("Nonempty frozen parameter mapping required")
    for key, item in value.items():
        if type(key) is not str or not _NAME.fullmatch(key):
            raise ValueError("Parameter names must be canonical lowercase slugs")
        if type(item) is bool or item is None:
            raise ValueError("Booleans/null are not research numeric parameters")
        if type(item) in (int, float):
            if not math.isfinite(item):
                raise ValueError("Nonfinite research parameter")
        elif type(item) is str:
            if not item or len(item) > 120:
                raise ValueError("Empty/oversized string parameter")
        else:
            raise ValueError("Nested, noncanonical or mutable parameter")


def validate_plan(plan: object) -> None:
    if type(plan) is not dict or set(plan) != _KEYS:
        raise ValueError("Preregistration requires exactly the frozen schema keys")
    if plan["schema"] != SCHEMA or plan["evidence_status"] != "FUTURE_UNOBSERVED_NOT_VALIDATED":
        raise ValueError("A prospective plan cannot certify trading performance")
    if type(plan["strategy"]) is not str or not _NAME.fullmatch(plan["strategy"]):
        raise ValueError("Invalid strategy identifier")
    for name, regex in (("strategy_blob_sha", _SHA40), ("training_archive_sha256", _SHA64)):
        if type(plan[name]) is not str or not regex.fullmatch(plan[name]):
            raise ValueError(f"Invalid {name}")
    stamp = _registered(plan["registered_at_utc"])
    exposed = _day(plan["known_exposed_through"], "known_exposed_through")
    train = _day(plan["train_end"], "train_end")
    start = _day(plan["holdout_start"], "holdout_start")
    end = _day(plan["holdout_end"], "holdout_end")
    if not (start > max(exposed, train, stamp.date()) and end >= start):
        raise ValueError("Prospective holdout must start AFTER registration, training and exposure")
    if type(plan["fee_usd_per_oz"]) not in (float, int) or plan["fee_usd_per_oz"] != 0.40:
        raise ValueError("Canonical all-in roundtrip cost must be exactly $0.40/oz")
    _parameters(plan["parameters"])


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def freeze_plan(plan: dict) -> dict:
    """Return a SHA-pinned JSON-safe envelope; caller must commit externally."""
    validate_plan(plan)
    frozen = json.loads(_canonical(plan))
    return {"plan": frozen, "sha256": hashlib.sha256(_canonical(frozen)).hexdigest()}


def verify_freeze(envelope: object) -> dict:
    if type(envelope) is not dict or set(envelope) != {"plan", "sha256"}:
        raise ValueError("Frozen envelope must contain only plan and sha256")
    plan = envelope["plan"]
    validate_plan(plan)
    digest = envelope["sha256"]
    if type(digest) is not str or not _SHA64.fullmatch(digest):
        raise ValueError("Malformed frozen plan digest")
    if hashlib.sha256(_canonical(plan)).hexdigest() != digest:
        raise ValueError("Preregistration was changed after freezing")
    return plan


def authorize_future_evaluation(envelope: dict, *, strategy_blob_sha: str,
                                observed_start: str, observed_end: str,
                                verified_external_commit_before: str) -> dict:
    """Guard ONLY; caller must independently verify Git commit time/provenance.

    verified_external_commit_before is a trusted timestamp from the external
    version-control audit, not a timestamp self-reported by this module.
    No outcome is automatically considered a verified edge.
    """
    plan = verify_freeze(envelope)
    external = _registered(verified_external_commit_before)
    if external < _registered(plan["registered_at_utc"]):
        raise ValueError("External commit predates claimed plan registration")
    if external.date() >= _day(plan["holdout_start"], "holdout_start"):
        raise ValueError("External freeze is not earlier than the holdout")
    if strategy_blob_sha != plan["strategy_blob_sha"]:
        raise ValueError("Strategy code changed after preregistration")
    start = _day(observed_start, "observed_start")
    end = _day(observed_end, "observed_end")
    if not (_day(plan["holdout_start"], "holdout_start") <= start <= end
            <= _day(plan["holdout_end"], "holdout_end")):
        raise ValueError("Evaluation period escapes the frozen prospective window")
    return plan
