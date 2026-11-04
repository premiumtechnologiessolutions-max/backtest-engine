"""Fail-closed native-export -> canonical-ledger -> parity construction pipeline.

Receives *local in-memory bytes* exported from pinned LEAN/Nautilus-shaped
interfaces, never starts those engines or reads Gold. Verifies complete
content hashes and sidecars, normalizes every declared comparator, and
invokes the existing independent row-by-row parity calculator.

A successful result only proves consistency of supplied bytes. The caller
can fabricate both bytes and hashes; this is NOT an authenticated vendor-run
attestation, broker-fill validation, OOS proof or accepted strategy result.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

import pandas as pd

from norisk_quant.campaign_blueprint import verify_blueprint
from norisk_quant.cross_engine_parity import (
    _normalize, compare_frozen_engine_ledgers,
)
from norisk_quant.upstream_trade_normalizers import (
    PINNED_VENDOR, normalize_lean_closed_trades,
    normalize_nautilus_positions_report,
)

SCHEMA = "NRFX_NATIVE_EXPORT_PARITY_PIPELINE_V1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_EXPORT_BYTES = 32 * 1024 * 1024
_MAX_SIDECAR_BYTES = 8 * 1024 * 1024
_MAX_ENTRIES = 100_000


@dataclass(frozen=True, slots=True)
class NativeExport:
    """Opaque local source bytes, one exact engine identity and frozen hashes."""
    engine: str
    export_bytes: bytes
    sidecar_bytes: bytes
    export_sha256: str
    sidecar_sha256: str
    vendor_commit: str
    instrument: str

    def __post_init__(self) -> None:
        if (type(self.engine) is not str or self.engine not in PINNED_VENDOR
                or type(self.export_bytes) is not bytes
                or not 1 <= len(self.export_bytes) <= _MAX_EXPORT_BYTES
                or type(self.sidecar_bytes) is not bytes
                or not 1 <= len(self.sidecar_bytes) <= _MAX_SIDECAR_BYTES
                or type(self.export_sha256) is not str
                or not _SHA.fullmatch(self.export_sha256)
                or type(self.sidecar_sha256) is not str
                or not _SHA.fullmatch(self.sidecar_sha256)
                or self.vendor_commit != PINNED_VENDOR[self.engine]
                or type(self.instrument) is not str
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", self.instrument)):
            raise ValueError("Invalid bounded/pinned native export contract")
        if hashlib.sha256(self.export_bytes).hexdigest() != self.export_sha256:
            raise ValueError("Native export actual bytes differ from expected SHA256")
        if hashlib.sha256(self.sidecar_bytes).hexdigest() != self.sidecar_sha256:
            raise ValueError("Native sidecar actual bytes differ from expected SHA256")


def _strict_json(raw: bytes) -> object:
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("Duplicate field in vendor export")
            obj[key] = value
        return obj
    def reject(value):
        raise ValueError("Nonfinite vendor export JSON value")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=reject)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed vendor export JSON") from exc


def _read_lean(export: NativeExport, mappings: dict) -> tuple[pd.DataFrame, dict]:
    obj = _strict_json(export.export_bytes)
    if (type(obj) is not dict or set(obj) != {"closedTrades"}
            or type(obj["closedTrades"]) is not list
            or len(obj["closedTrades"]) > _MAX_ENTRIES):
        raise ValueError("Expected closedTrades export, not arbitrary LEAN result")
    return normalize_lean_closed_trades(
        obj["closedTrades"], mappings,
        expected_sidecar_sha256=_canonical_sha(mappings),
        source_symbol=export.instrument, vendor_commit=export.vendor_commit,
    )


def _read_nautilus(export: NativeExport, mappings: dict) -> tuple[pd.DataFrame, dict]:
    obj = _strict_json(export.export_bytes)
    if (type(obj) is not dict or set(obj) != {"index_name", "rows"}
            or obj["index_name"] != "position_id"
            or type(obj["rows"]) is not list
            or len(obj["rows"]) > _MAX_ENTRIES):
        raise ValueError("Expected explicitly exported Nautilus positions DataFrame")
    rows = obj["rows"]
    if any(type(item) is not dict or "position_id" not in item for item in rows):
        raise ValueError("Missing native Nautilus position identifier")
    # The bridge export must supply one row per closed source position. No
    # summing/reconstructing partial fills or silently discarding snapshots.
    frame = pd.DataFrame(rows)
    if "position_id" not in frame.columns:
        frame = pd.DataFrame(columns=["position_id"])
    frame = frame.set_index("position_id")
    return normalize_nautilus_positions_report(
        frame, mappings,
        expected_sidecar_sha256=_canonical_sha(mappings),
        instrument_id=export.instrument, vendor_commit=export.vendor_commit,
    )


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")).hexdigest()


def _build_native_export_parity(
    blueprint: dict,
    nrfx_ledger: pd.DataFrame,
    vendor_exports: dict[str, NativeExport],
) -> dict:
    """Validate every vendor report and compare it to the NRFX native ledger.

    Inputs are local in-memory Python objects. No subprocess, file path, URL,
    credentials, network access or broker order is supported by this API.
    """
    frozen = verify_blueprint(blueprint)
    expected = set(frozen["normalized_spec"]["execution_engines"])
    external = expected - {"norisk_quant"}
    if (not external or not external <= set(PINNED_VENDOR)
            or type(vendor_exports) is not dict or set(vendor_exports) != external):
        raise ValueError("Every frozen vendor comparator must be supplied exactly once")
    strategies = {s["id"] for s in frozen["normalized_spec"]["strategies"]}
    _normalize("norisk_quant", nrfx_ledger, strategies)
    ledgers = {"norisk_quant": nrfx_ledger}
    manifests = {}
    for engine in sorted(external):
        export = vendor_exports[engine]
        if type(export) is not NativeExport or export.engine != engine:
            raise ValueError("Vendor export engine identity mismatches frozen plan")
        mappings = _strict_json(export.sidecar_bytes)
        if type(mappings) is not dict:
            raise ValueError("Source sidecar must be an exact mapping object")
        # The existing source-shaped converters verify bijection between
        # every source row ID and every sidecar ID and reject partials.
        if engine == "lean":
            frame, metadata = _read_lean(export, mappings)
        else:
            frame, metadata = _read_nautilus(export, mappings)
        if metadata["normalized_trade_count"] != len(frame):
            raise ValueError("Native row normalization dropped source trades")
        ledgers[engine] = frame
        manifests[engine] = {
            "engine": engine,
            "pinned_vendor_commit": export.vendor_commit,
            "raw_source_bytes_sha256": export.export_sha256,
            "source_sidecar_bytes_sha256": export.sidecar_sha256,
            "source_sidecar_canonical_sha256": _canonical_sha(mappings),
            "normalized_ledger_sha256": metadata["normalized_ledger_sha256"],
            "source_rows": metadata["source_rows"],
            "status": metadata["status"],
            "vendor_execution_attested": False,
        }
    comparison = compare_frozen_engine_ledgers(frozen, ledgers)
    # A source sidecar hash is only a byte identity; its *pre-run origin*
    # must be independently attested by a future isolated vendor executor.
    result = {
        "schema": SCHEMA,
        "blueprint_sha256": frozen["blueprint_sha256"],
        "provider_exports": manifests,
        "parity_diagnostic": comparison,
        "status": "NATIVE_EXPORTS_PARSED_AND_COMPARED_UNVERIFIED",
        "all_planned_providers_included": True,
        "external_runtime_attested": False,
        "sidecar_preexecution_freeze_attested": False,
        "quote_provenance_attested": False,
        "independent_fill_events_attested": False,
        "original_gold_archive_accessed": False,
        "external_engine_started": False,
        "research_result_accepted": False,
    }
    return {**result, "pipeline_sha256": _canonical_sha(result)}, ledgers


def normalize_and_compare_native_exports(
    blueprint: dict,
    nrfx_ledger: pd.DataFrame,
    vendor_exports: dict[str, NativeExport],
) -> dict:
    """Return only serializable audit metadata, never raw trade rows."""
    report, _ = _build_native_export_parity(blueprint, nrfx_ledger, vendor_exports)
    return report
