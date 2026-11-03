"""Immutable experiment fingerprints for cross-chat and cross-run reproducibility.

A fingerprint is NOT proof that a backtest executed or was independently
validated. Git commit and data source hash must be provided explicitly.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import math

import pandas as pd
from dataclasses import asdict, dataclass, field
from typing import Any

_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class ExperimentIdentity:
    dataset_sha256: str
    engine_commit: str
    strategy_id: str
    parameters: dict[str, Any]
    timeframe: str
    window_start_utc: str
    window_end_exclusive_utc: str
    quantity_ounces: float
    fee_all_in_per_ounce: float = 0.40
    execution_mode: str = "m1_conservative"
    protocol_version: str = "0.1"
    exposure_context: str = "historical_exposed"
    notes: str = ""

    def __post_init__(self) -> None:
        if not _HEX64.fullmatch(self.dataset_sha256):
            raise ValueError("dataset_sha256 must be a full SHA-256 fingerprint")
        if not re.fullmatch(r"[0-9a-fA-F]{40}", self.engine_commit):
            raise ValueError("engine_commit must be an immutable full 40-char Git commit")
        if not self.strategy_id or not self.timeframe:
            raise ValueError("Missing strategy identity")
        if (type(self.quantity_ounces) not in (int, float)
                or type(self.fee_all_in_per_ounce) not in (int, float)
                or not math.isfinite(self.quantity_ounces)
                or not math.isfinite(self.fee_all_in_per_ounce)):
            raise ValueError("Nonfinite or invalid quantity/fee")
        if self.quantity_ounces <= 0 or self.fee_all_in_per_ounce < 0:
            raise ValueError("Invalid quantity or fixed all-in fee")
        if self.execution_mode not in ("m1_conservative", "observed_tick_research"):
            raise ValueError("Unsupported execution mode")
        if self.exposure_context not in ("training", "historical_exposed", "future_prospective"):
            raise ValueError("Unknown exposure context")
        start = pd.Timestamp(self.window_start_utc)
        end = pd.Timestamp(self.window_end_exclusive_utc)
        if start.tzinfo is None or end.tzinfo is None or not start < end:
            raise ValueError("Experiment window must be chronological and timezone-aware")
        # Snapshot the nested parameter tree at construction. A frozen dataclass
        # does not freeze its mutable dict: silently changing it after an ID is
        # issued would make historical manifests and their fingerprints drift.
        if type(self.parameters) is not dict:
            raise ValueError("Parameters must be a JSON object")
        try:
            frozen = json.dumps(self.parameters, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False, allow_nan=False)
            parsed = json.loads(frozen)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Parameters must be finite JSON values") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Parameters must be a JSON object")
        object.__setattr__(self, "_parameters_snapshot", frozen)
        if not math.isfinite(self.quantity_ounces) or not math.isfinite(self.fee_all_in_per_ounce):
            raise ValueError("Nonfinite quantity or fee")
        if self.execution_mode == "observed_tick_research":
            # This prototype cannot run an observed tick event engine yet.
            raise ValueError("Observed tick execution is not implemented")
        if type(self.parameters) is not dict:
            raise ValueError("Parameters require finite JSON mapping")
        try:
            frozen = json.dumps(
                self.parameters, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            )
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("Parameters require finite JSON values") from exc
        # Frozen dataclass does not recursively freeze caller-owned mappings.
        # Pin exact original bytes and reject later mutation before fingerprint
        # or manifest generation instead of silently changing experiment ID.
        object.__setattr__(self, "_frozen_parameters_json", frozen)


def _checked_fields(identity: ExperimentIdentity) -> dict:
    fields = asdict(identity)
    if json.dumps(fields['parameters'], sort_keys=True, separators=(',', ':'),
                  ensure_ascii=False, allow_nan=False) != identity._parameters_snapshot:
        raise ValueError('Experiment parameters mutated after identity was frozen')
    return fields


def _numeric_canonical(value):
    """Normalize equivalent JSON integer/float parameter values."""
    if type(value) is dict:
        return {key: _numeric_canonical(part) for key, part in value.items()}
    if type(value) is list:
        return [_numeric_canonical(part) for part in value]
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Parameters require finite JSON values")
        if value.is_integer() and abs(value) <= 2 ** 53:
            return int(value)
    return value


def _ensure_frozen_parameters(identity: ExperimentIdentity) -> None:
    try:
        current = json.dumps(
            identity.parameters, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Experiment parameters mutated or invalid") from exc
    if current != identity._frozen_parameters_json:
        raise ValueError("Experiment parameters mutated after freezing")


def fingerprint(identity: ExperimentIdentity) -> str:
    _ensure_frozen_parameters(identity)
    fields = asdict(identity)
    # Editorial notes must not generate a new experiment ID.
    fields.pop("notes")
    fields["parameters"] = _numeric_canonical(
        json.loads(identity._frozen_parameters_json))
    canonical = json.dumps(
        fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def experiment_manifest(identity: ExperimentIdentity) -> dict:
    return {
        "experiment_id": fingerprint(identity),
        "identity": asdict(identity),
        "execution_status": "DEFINED_ONLY",
        "independent_test_proven": False,
        "disclaimer": (
            "Fingerprint establishes reproducible intent, not that execution "
            "happened or that a strategy has profitable independent performance."
        ),
    }
