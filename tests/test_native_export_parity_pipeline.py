"""Strict synthetic export pipeline; no LEAN/Nautilus executable invoked."""
import hashlib
import json

import pandas as pd
import pytest

from norisk_quant.campaign_blueprint import freeze_blueprint
from norisk_quant.native_export_parity_pipeline import (
    NativeExport, normalize_and_compare_native_exports,
)
from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(obj):
    return json.dumps(obj, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def blueprint():
    return freeze_blueprint({
        "source_commit": "a" * 40,
        "dataset": {"id": "xauusd_m1", "archive_sha256": "b" * 64,
                    "start": "2026-01-01", "end": "2026-01-31",
                    "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2026-01-01", "end": "2026-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [{"id": "bos_fib", "code_sha256": "c" * 64,
                        "spec_sha256": "d" * 64}],
        "execution_engines": ["lean", "nautilus", "norisk_quant"],
        "ai_reviewers": [],
        "resource_limits": {"max_workers": 2, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.4,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    })


def nrfx():
    return pd.DataFrame([{
        "trade_id": "bos_fib_001", "strategy": "bos_fib",
        "signal_at": "2026-01-05T10:00:00Z",
        "entry_at": "2026-01-05T10:01:00Z",
        "closed_at": "2026-01-05T10:04:00Z",
        "side": 1, "entry_price": 2000., "exit_price": 2003.,
        "stop": 1995., "target": 2005., "ounces": 1.,
        "gross_pnl": 3., "cost": 0.4, "net_pnl": 2.6,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }])


def sidecar():
    return {"trade_id": "bos_fib_001", "strategy": "bos_fib",
            "signal_at": "2026-01-05T10:00:00Z", "stop": 1995.,
            "target": 2005., "exit_reason": "time_exit", "gap_minutes": 0}


def make(engine, report, id_, symbol, *, side=None):
    mapping = {id_: side if side is not None else sidecar()}
    raw, mraw = dump(report), dump(mapping)
    return NativeExport(
        engine, raw, mraw, digest(raw), digest(mraw),
        PINNED_VENDOR[engine], symbol,
    )


def inputs():
    lean = make("lean", {"closedTrades": [{
        "id": "L001", "symbols": ["XAUUSD"],
        "entryTime": "2026-01-05T10:01:00Z",
        "exitTime": "2026-01-05T10:04:00Z",
        "direction": 0, "quantity": 1.,
        "entryPrice": 2000., "exitPrice": 2003.,
        "profitLoss": 3., "totalFees": .4,
    }]}, "L001", "XAUUSD")
    naut = make("nautilus", {"index_name": "position_id", "rows": [{
        "position_id": "P001", "instrument_id": "XAUUSD.SIM",
        "strategy_id": "bos_fib", "entry": "BUY", "side": "FLAT",
        "quantity": "0", "peak_qty": "1",
        "avg_px_open": "2000", "avg_px_close": "2003",
        "commissions": ["0.40 USD"], "realized_pnl": "2.60 USD",
        "ts_opened": "2026-01-05T10:01:00Z",
        "ts_closed": "2026-01-05T10:04:00Z",
        "is_snapshot": False,
    }]}, "P001", "XAUUSD.SIM")
    return {"lean": lean, "nautilus": naut}


def test_native_exports_flow_into_full_row_parity():
    result = normalize_and_compare_native_exports(blueprint(), nrfx(), inputs())
    parity = result["parity_diagnostic"]
    assert parity["status"] == "ROW_PARITY_MATCH_UNVERIFIED"
    assert parity["field_discrepancy_count"] == 0
    assert result["pipeline_sha256"]
    assert all(result["provider_exports"][key]["source_rows"] == 1
               for key in ("lean", "nautilus"))
    assert result["external_engine_started"] is False
    assert result["research_result_accepted"] is False


def test_missing_vendor_cannot_silently_be_excluded():
    incomplete = inputs()
    del incomplete["nautilus"]
    with pytest.raises(ValueError, match="Every frozen vendor"):
        normalize_and_compare_native_exports(blueprint(), nrfx(), incomplete)


def test_raw_export_sha256_is_rechecked_against_bytes():
    a = inputs()["lean"]
    with pytest.raises(ValueError, match="actual bytes"):
        NativeExport(a.engine, a.export_bytes + b"x", a.sidecar_bytes,
                     a.export_sha256, a.sidecar_sha256,
                     a.vendor_commit, a.instrument)


def test_modified_sidecar_fingerprint_is_rejected():
    a = inputs()["lean"]
    with pytest.raises(ValueError, match="sidecar actual bytes"):
        NativeExport(a.engine, a.export_bytes, a.sidecar_bytes + b"x",
                     a.export_sha256, a.sidecar_sha256,
                     a.vendor_commit, a.instrument)


def test_duplicate_json_fields_refused_even_with_correct_sha():
    a = inputs()
    raw = b'{"closedTrades":[],"closedTrades":[]}'
    a["lean"] = NativeExport(
        "lean", raw, a["lean"].sidecar_bytes, digest(raw),
        a["lean"].sidecar_sha256, PINNED_VENDOR["lean"], "XAUUSD")
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_and_compare_native_exports(blueprint(), nrfx(), a)


def test_no_nautilus_position_may_be_filtered_by_adapter():
    a = inputs()
    raw = dump({"index_name": "position_id", "rows": []})
    a["nautilus"] = NativeExport(
        "nautilus", raw, a["nautilus"].sidecar_bytes,
        digest(raw), a["nautilus"].sidecar_sha256,
        PINNED_VENDOR["nautilus"], "XAUUSD.SIM")
    with pytest.raises(ValueError):
        normalize_and_compare_native_exports(blueprint(), nrfx(), a)


def test_mismatched_engine_binding_or_vendor_version_fails():
    a = inputs()
    a["lean"] = a["nautilus"]
    with pytest.raises(ValueError, match="identity"):
        normalize_and_compare_native_exports(blueprint(), nrfx(), a)
    b = inputs()["lean"]
    with pytest.raises(ValueError, match="pinned"):
        NativeExport("lean", b.export_bytes, b.sidecar_bytes,
                     b.export_sha256, b.sidecar_sha256,
                     "0" * 40, "XAUUSD")


def test_reversed_chronology_cannot_be_hidden_in_report():
    a = inputs()
    changed = {"closedTrades": [{
        "id": "L001", "symbols": ["XAUUSD"],
        "entryTime": "2026-01-05T10:08:00Z",
        "exitTime": "2026-01-05T10:04:00Z",
        "direction": 0, "quantity": 1.,
        "entryPrice": 2000., "exitPrice": 2003.,
        "profitLoss": 3., "totalFees": .4,
    }]}
    a["lean"] = make("lean", changed, "L001", "XAUUSD")
    with pytest.raises(ValueError, match="chronology"):
        normalize_and_compare_native_exports(blueprint(), nrfx(), a)


def test_net_pnl_disagreement_even_with_matching_export_structure():
    a = inputs()
    changed = {"closedTrades": [{
        "id": "L001", "symbols": ["XAUUSD"],
        "entryTime": "2026-01-05T10:01:00Z",
        "exitTime": "2026-01-05T10:04:00Z",
        "direction": 0, "quantity": 1.,
        "entryPrice": 2001., "exitPrice": 2004.,
        "profitLoss": 3., "totalFees": .4,
    }]}
    a["lean"] = make("lean", changed, "L001", "XAUUSD")
    result = normalize_and_compare_native_exports(blueprint(), nrfx(), a)
    assert result["parity_diagnostic"]["field_discrepancy_count"] >= 2
    assert result["research_result_accepted"] is False


def test_nonfinite_or_unbounded_export_refused():
    a = inputs()
    raw = b'{"closedTrades":[NaN]}'
    a["lean"] = NativeExport(
        "lean", raw, a["lean"].sidecar_bytes,
        digest(raw), a["lean"].sidecar_sha256,
        PINNED_VENDOR["lean"], "XAUUSD")
    with pytest.raises(ValueError, match="Nonfinite"):
        normalize_and_compare_native_exports(blueprint(), nrfx(), a)
    b = a["nautilus"]
    with pytest.raises(ValueError):
        NativeExport("nautilus", b"x" * (32 * 1024 * 1024 + 1), b.sidecar_bytes,
                     digest(b"x" * (32 * 1024 * 1024 + 1)),
                     b.sidecar_sha256, PINNED_VENDOR["nautilus"], "XAUUSD.SIM")
