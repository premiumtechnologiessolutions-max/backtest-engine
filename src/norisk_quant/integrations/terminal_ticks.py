"""Fail-closed NoRiskFX Terminal v0.19.1 tick-snapshot intake.

The private Terminal exports a read-only, source-scoped *research request*.
This adapter accepts its declared tick evidence, NOT Terminal's simulation
results, and passes only normalized quotes to the canonical XAUUSD lab.
It never logs or returns account scope, raw source data, or any credentials.
It never makes a trading decision, simulates a fill or applies an execution fee.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import re
import struct
from typing import Any

import pandas as pd

from norisk_quant.ticks import TickSource, normalize_ticks

SCHEMA_VERSION = "noriskfx-terminal-tick-import-v1"
MAX_BYTES = 80_000_000
MAX_TICKS = 250_000
ASSETS = frozenset({"XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF"})
TOP_LEVEL = frozenset({"data_kind", "frame", "contract", "config", "source_evidence", "ticks"})
CONTRACT_KEYS = frozenset({"asset", "instrument", "provider", "provider_scope", "account_currency", "quote_currency", "point_size", "unit_step", "minimum_units"})
CONFIG_KEYS = frozenset({"capital", "risk_pct", "commission_per_side", "slippage_points", "latency_ms", "max_quote_gap_seconds", "max_hold_seconds"})
EVIDENCE_KEYS = frozenset({"origin", "collector_version", "captured_at", "server_time_offset_seconds", "time_basis", "time_source_url", "denomination_source_url", "denomination_factor", "units_per_lot", "account_kind", "commission_status"})
TICK_KEYS = frozenset({"at", "seq", "bid", "ask", "quote_to_account", "conversion_source"})
UTC_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)\Z")
TEXT = re.compile(r"[\w .:/+·\-()]{1,120}\Z", re.UNICODE)


@dataclass(frozen=True)
class TerminalTickImport:
    """Research-only result; market quotes remain local and never enter Git."""

    ticks: pd.DataFrame
    source: TickSource
    evidence: dict[str, Any]


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key in Terminal input")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid non-finite JSON constant: {value}")


def _object(value: object, label: str, *, allowed: frozenset[str], required: frozenset[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - allowed or required - set(value):
        raise ValueError(f"Invalid {label} schema: missing or unexpected keys")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not TEXT.fullmatch(value):
        raise ValueError(f"Invalid {label} metadata")
    return value


def _positive(value: object, label: str, *, allow_zero: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value > 1e12 or (value < 0 if allow_zero else value <= 0):
        raise ValueError(f"Invalid numeric {label}")
    return float(value)


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not UTC_FORMAT.fullmatch(value):
        raise ValueError("Terminal ticks require explicit canonical UTC timestamps")
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid Terminal tick timestamp") from exc
    if date.utcoffset() != timedelta(0):
        raise ValueError("Terminal ticks must already be UTC-normalized")
    return date.astimezone(timezone.utc)


def _validate_contract(raw: object, kind: str) -> dict[str, Any]:
    contract = _object(raw, "contract", allowed=CONTRACT_KEYS, required=CONTRACT_KEYS)
    for field in ("asset", "instrument", "provider", "provider_scope", "account_currency", "quote_currency"):
        _text(contract[field], field)
    asset = contract["asset"]
    if asset not in ASSETS:
        raise ValueError("Terminal adapter supports only XAUUSD and the seven major forex pairs")
    if contract["quote_currency"] != ("USD" if asset == "XAUUSD" else asset[3:]):
        raise ValueError("Quote currency does not match symbol")
    if not re.fullmatch(r"[A-Z]{3,4}", contract["account_currency"]):
        raise ValueError("Invalid account-currency label")
    if kind == "broker_history" and not re.fullmatch(r"[a-f0-9]{64}", contract["provider_scope"]):
        raise ValueError("Broker source scope must be an opaque SHA256 identifier")
    for name in ("point_size", "unit_step", "minimum_units"):
        _positive(contract[name], name)
    return contract


def _validate_config(raw: object) -> None:
    # Terminal's own simulation config is NOT a canonical-engine cost model.
    # Validate and discard rather than unintentionally importing its fees.
    if raw is None:
        return
    config = _object(raw, "simulation config", allowed=CONFIG_KEYS)
    for name, value in config.items():
        _positive(value, name, allow_zero=name in {"commission_per_side", "slippage_points", "latency_ms"})
    if config.get("risk_pct", 0.1) > 2 or config.get("latency_ms", 250) > 1000:
        raise ValueError("Out-of-bound Terminal simulation config")


def _validate_evidence(raw: object) -> None:
    if raw is None:
        return
    evidence = _object(raw, "source evidence", allowed=EVIDENCE_KEYS)
    for key, value in evidence.items():
        if key in {"server_time_offset_seconds", "denomination_factor", "units_per_lot"}:
            _positive(value, key, allow_zero=key == "server_time_offset_seconds")
        elif not isinstance(value, str) or len(value) > 500:
            raise ValueError(f"Invalid source-evidence {key}")
    # No claim of authenticated source merely because an importer declares one.


def import_terminal_ticks(payload: bytes, *, allow_synthetic: bool = False) -> TerminalTickImport:
    """Normalize one *private* Terminal JSON snapshot, without running a strategy.

    The stable quote fingerprint changes with feed scope, contract and each
    ordered observed tick. Source-bytes SHA separately detects file edits.
    Both are evidence IDs, not broker authentication. Missing conversion
    factors and non-UTC server-time exports are rejected, never invented.
    """
    if type(payload) is not bytes or not 1 <= len(payload) <= MAX_BYTES:
        raise ValueError("Terminal JSON must be nonempty bytes within the 80 MB limit")
    try:
        request = json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicates,
                             parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed Terminal UTF-8 JSON input") from exc
    request = _object(request, "Terminal request", allowed=TOP_LEVEL,
                      required=frozenset({"data_kind", "frame", "contract", "ticks"}))
    kind, frame = request["data_kind"], request["frame"]
    if kind not in ("broker_history", "synthetic_test") or frame not in ("M1", "M5"):
        raise ValueError("Unsupported Terminal dataset kind or research timeframe")
    if kind == "synthetic_test" and not allow_synthetic:
        raise ValueError("Synthetic Terminal data requires explicit opt in")
    contract = _validate_contract(request["contract"], kind)
    _validate_config(request.get("config"))
    _validate_evidence(request.get("source_evidence"))
    source_evidence = request.get("source_evidence") or {}
    cent_denomination = contract["quote_currency"] == "USD" and contract["account_currency"] == "USC"
    if cent_denomination:
        expected_factor = source_evidence.get("denomination_factor")
        if (type(expected_factor) not in (int, float)
                or not math.isfinite(expected_factor) or expected_factor <= 0):
            raise ValueError("USC source requires an explicit positive denomination factor")
        if kind == "broker_history" and source_evidence.get("account_kind") != "real_cent_read_only":
            raise ValueError("VT Cent history requires explicit Cent account provenance")
        if (kind == "broker_history" and contract["provider"] == "VT Markets MT5 · Cent"
                and expected_factor != 100):
            raise ValueError("VT Cent must use 100 USC per USD")
    rows = request["ticks"]
    if not isinstance(rows, list) or not 2 <= len(rows) <= MAX_TICKS:
        raise ValueError("Terminal dataset must contain 2–250000 observed ticks")

    digest = sha256()
    digest.update((SCHEMA_VERSION + "\0").encode("ascii"))
    # Context binds a quote fingerprint to the source account scope and unit
    # interpretation without ever returning the raw scope from this adapter.
    context = json.dumps({"contract": contract, "frame": frame, "data_kind": kind},
                         sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    digest.update(context.encode("utf-8"))
    digest.update(b"\0")
    normalized: list[dict[str, Any]] = []
    previous_ts: datetime | None = None
    previous_seq = -1
    for row in rows:
        row = _object(row, "tick", allowed=TICK_KEYS, required=frozenset({"at", "seq", "bid", "ask"}))
        at = _utc(row["at"])
        seq = row["seq"]
        if type(seq) is not int or seq <= previous_seq or seq >= 2**53:
            raise ValueError("Terminal tick sequence must strictly increase and be an exact integer")
        if previous_ts is not None and at < previous_ts:
            raise ValueError("Terminal tick timestamps cannot run backwards")
        bid, ask = _positive(row["bid"], "bid"), _positive(row["ask"], "ask")
        if ask < bid:
            raise ValueError("Crossed Terminal quote")
        if contract["quote_currency"] == contract["account_currency"]:
            factor = _positive(row.get("quote_to_account", 1), "quote_to_account")
            if factor != 1:
                raise ValueError("Matching currencies must use conversion factor one")
        else:
            if "conversion_source" not in row:
                raise ValueError("Historical quote/account conversion requires evidence on each tick")
            _text(row["conversion_source"], "conversion_source")
            factor = _positive(row.get("quote_to_account"), "quote_to_account")
        if cent_denomination and factor != float(source_evidence["denomination_factor"]):
            raise ValueError("USC denomination must stay constant on every observed tick")
        if at.year < 1970 or at.year > 2100:
            raise ValueError("Tick outside supported UTC clock range")
        ts_ns = int(pd.Timestamp(at).value)
        digest.update(struct.pack(">qQddd", ts_ns, seq, bid, ask, factor))
        normalized.append({"ts_utc": at.isoformat(), "seq": seq, "bid": bid, "ask": ask,
                           "quote_to_account": factor})
        previous_ts, previous_seq = at, seq

    source = TickSource(provider=contract["provider"], symbol=contract["instrument"],
                        source_kind="synthetic" if kind == "synthetic_test" else "declared_broker_ticks")
    ticks = normalize_ticks(pd.DataFrame.from_records(normalized), source, allow_synthetic=allow_synthetic)
    fingerprint = digest.hexdigest()
    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_bytes_sha256": sha256(payload).hexdigest(),
        "quote_context_sha256": fingerprint,
        "provider_declared": contract["provider"],
        "symbol_declared": contract["instrument"],
        "source_kind_declared": kind,
        "source_authentication": "NOT_VERIFIED",
        "account_currency_label": contract["account_currency"],
        "quote_currency_label": contract["quote_currency"],
        "ticks": len(ticks),
        "first_utc": ticks.index[0].isoformat(),
        "last_utc": ticks.index[-1].isoformat(),
        "cost_model": "NOT_APPLIED_DATA_ONLY",
        "execution": "NONE_RESEARCH_IMPORT",
        "simulation_results_imported": False,
        "independent_oos": False,
        "broker_fill_parity": False,
        "notice": "Declared broker quotes are not authenticated fills; source simulation fees are not transferred.",
    }
    return TerminalTickImport(ticks=ticks, source=source, evidence=evidence)
