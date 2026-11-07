"""Machine-verifiable FAC025 preregistered *filter* grid, not a backtest.

The research hypothesis and all 72 correlated filter settings were frozen in
FAC025_FROZEN_CAUSAL_NY_SESSION_RISK_GATE_2026-10-28.md. This module makes
those settings reproducible without optimizing against historical outcomes.
It deliberately defines NO entry/exit rule or execution result.
"""
from __future__ import annotations

from hashlib import sha256
from itertools import product
import json

HYPOTHESIS = "NRF-FAC-025"
SPEC_VERSION = 1
FROZEN_FEE_USD_PER_OZ = "0.40"
FROZEN_MAX_ENTRY_DELAY_MINUTES = 1
FROZEN_CAPACITY = 1
FIELDS = ("lookback", "min_range_ratio", "max_range_ratio",
          "daily_loss_halt", "session_start_hour", "session_end_hour")
# Decimal strings are intentional: canonical fingerprints must not depend on
# floating-point repr or a research worker's runtime/platform.
LOOKBACKS = (4, 8, 12)
MIN_RATIOS = ("0.0004", "0.0008")
MAX_RATIOS = ("0.003", "0.006")
LOSS_HALTS = ("2", "4", "6")
SESSIONS = ((8, 12), (9, 13))


def _payload(parameters: dict) -> bytes:
    return json.dumps({"hypothesis": HYPOTHESIS, "spec_version": SPEC_VERSION,
                       "parameters": parameters}, sort_keys=True,
                      ensure_ascii=True, separators=(",", ":")).encode("ascii")


def frozen_specs() -> tuple[dict, ...]:
    """Return the exact 72 frozen correlated filter settings with stable IDs."""
    out = []
    for lookback, low, high, halt, session in product(
            LOOKBACKS, MIN_RATIOS, MAX_RATIOS, LOSS_HALTS, SESSIONS):
        parameters = dict(zip(FIELDS, (lookback, low, high, halt, *session)))
        out.append({"id": f"FAC025-{len(out)+1:03d}",
                    "fingerprint": sha256(_payload(parameters)).hexdigest(),
                    "parameters": parameters})
    return tuple(out)


def validate_frozen_spec(parameters: object, fingerprint: object) -> dict:
    """Fail closed on mutated grid, extra fields, boolean/int confusion or ID reuse.

    This does not authenticate the original frozen document, certify M1 data,
    or authorize trading. The caller must independently pin the source commit.
    """
    if type(parameters) is not dict or tuple(parameters) != FIELDS:
        raise ValueError("FAC025 parameters differ from frozen schema/order")
    if type(fingerprint) is not str or len(fingerprint) != 64:
        raise ValueError("Invalid FAC025 fingerprint")
    if any(type(parameters[k]) is not type(spec["parameters"][k])
           for k in FIELDS for spec in frozen_specs()[:1]):
        raise ValueError("Invalid FAC025 parameter types")
    digest = sha256(_payload(parameters)).hexdigest()
    if digest != fingerprint:
        raise ValueError("FAC025 parameter fingerprint mismatch")
    for spec in frozen_specs():
        if spec["fingerprint"] == digest and spec["parameters"] == parameters:
            return spec
    raise ValueError("FAC025 parameter choice was not preregistered")


def frozen_manifest() -> dict:
    specs = frozen_specs()
    if len(specs) != 72 or len({s["fingerprint"] for s in specs}) != 72:
        raise AssertionError("FAC025 frozen grid cardinality/identity changed")
    digest = sha256(b"\n".join(s["fingerprint"].encode("ascii") for s in specs)).hexdigest()
    return {"hypothesis": HYPOTHESIS, "hypothesis_count": 1,
            "correlated_parameter_specs": 72, "grid_sha256": digest,
            "executed_original_source_backtests": 0,
            "monthly_pnl": "N/A", "floating_m1_drawdown": "N/A",
            "entry_exit_defined": False, "shared_capacity_verified": False,
            "status": "FROZEN_FILTER_ONLY_NOT_EXECUTED"}
