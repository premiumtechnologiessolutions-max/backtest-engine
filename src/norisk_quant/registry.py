"""Immutable experiment fingerprints for cross-chat and cross-run reproducibility.

A fingerprint is NOT proof that a backtest executed or was independently
validated. Git commit and data source hash must be provided explicitly.
"""
from __future__ import annotations

import hashlib
import json
import re

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
        if self.execution_mode == "observed_tick_research":
            # This prototype cannot run an observed tick event engine yet.
            raise ValueError("Observed tick execution is not implemented")


def fingerprint(identity: ExperimentIdentity) -> str:
    fields = asdict(identity)
    # Editorial notes must not generate a new experiment ID.
    fields.pop("notes")
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
