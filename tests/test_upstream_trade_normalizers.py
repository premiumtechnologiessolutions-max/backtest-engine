"""True upstream-shaped normalization tests using synthetic reports only."""
import hashlib
import json

import pandas as pd
import pytest

from norisk_quant.upstream_trade_normalizers import (
    PINNED_VENDOR, normalize_lean_closed_trades,
    normalize_nautilus_positions_report,
)
from norisk_quant.cross_engine_parity import compare_frozen_engine_ledgers
from norisk_quant.campaign_blueprint import freeze_blueprint


def sidecar():
    return {
        "trade_id": "bos_fib_0001",
        "strategy": "bos_fib",
        "signal_at": "2026-01-05T10:00:00Z",
        "stop": 1995.0, "target": 2005.0,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }


def pinned(s):
    return hashlib.sha256(json.dumps(
        s, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
        allow_nan=False).encode("ascii")).hexdigest()


def lean():
    return [{
        "id": "lean-guid-001",
        "symbols": ["XAUUSD"],
        "entryTime": "2026-01-05T10:01:00Z",
        "exitTime": "2026-01-05T10:04:00Z",
        "direction": 0, "quantity": 1.0,
        "entryPrice": 2000.0, "exitPrice": 2003.0,
        "profitLoss": 3.0, "totalFees": 0.4,
    }]


def nautilus():
    data = [{
        "position_id": "P-001", "instrument_id": "XAUUSD.SIM",
        "strategy_id": "bos_fib", "entry": "BUY", "side": "FLAT",
        "quantity": "0", "peak_qty": "1",
        "avg_px_open": "2000.0", "avg_px_close": "2003.0",
        "commissions": ["0.40 USD"], "realized_pnl": "2.60 USD",
        "ts_opened": "2026-01-05T10:01:00Z",
        "ts_closed": "2026-01-05T10:04:00Z",
        "is_snapshot": False,
    }]
    return pd.DataFrame(data).set_index("position_id")


def frozen():
    return freeze_blueprint({
        "source_commit": "a" * 40,
        "dataset": {
            "id": "xauusd_m1", "archive_sha256": "b" * 64,
            "start": "2026-01-01", "end": "2026-01-31",
            "format": "M1_BID_ASK_ORIGINAL",
        },
        "evaluation": {
            "start": "2026-01-01", "end": "2026-01-31",
            "scope": "UNEXECUTED_RESEARCH_DESIGN",
        },
        "strategies": [{"id": "bos_fib", "code_sha256": "c" * 64,
                        "spec_sha256": "d" * 64}],
        "execution_engines": ["norisk_quant", "lean", "nautilus"],
        "ai_reviewers": [],
        "resource_limits": {"max_workers": 2, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.4,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    })


def outputs():
    lean_sidecar = {"lean-guid-001": sidecar()}
    naut_sidecar = {"P-001": sidecar()}
    converted_lean, lm = normalize_lean_closed_trades(
        lean(), lean_sidecar, expected_sidecar_sha256=pinned(lean_sidecar),
        source_symbol="XAUUSD", vendor_commit=PINNED_VENDOR["lean"])
    converted_naut, nm = normalize_nautilus_positions_report(
        nautilus(), naut_sidecar,
        expected_sidecar_sha256=pinned(naut_sidecar),
        instrument_id="XAUUSD.SIM", vendor_commit=PINNED_VENDOR["nautilus"])
    return converted_lean, converted_naut, lm, nm


def test_source_specific_trade_reports_normalize_to_same_ledger():
    l, n, lm, nm = outputs()
    assert l.equals(n)
    assert lm["normalized_trade_count"] == 1
    assert nm["normalized_trade_count"] == 1
    assert lm["provider_execution_attested"] is False
    assert nm["sidecar_was_frozen_before_execution_proven"] is False
    assert l.iloc[0]["net_pnl"] == pytest.approx(2.6)


def test_source_adapters_feed_multi_engine_parity_without_running_engines():
    l, n, lm, nm = outputs()
    report = compare_frozen_engine_ledgers(frozen(), {
        "norisk_quant": l.copy(), "lean": l, "nautilus": n})
    assert report["status"] == "ROW_PARITY_MATCH_UNVERIFIED"
    assert report["field_discrepancy_count"] == 0
    assert report["upstream_engine_execution_attested"] is False
    assert report["strategy_research_accepted"] is False


def test_lean_mismatched_fees_or_account_conversion_rejected():
    source = lean()
    source[0]["totalFees"] = 0.0
    sc = {"lean-guid-001": sidecar()}
    with pytest.raises(ValueError, match="gross/fee"):
        normalize_lean_closed_trades(
            source, sc, expected_sidecar_sha256=pinned(sc),
            source_symbol="XAUUSD", vendor_commit=PINNED_VENDOR["lean"])


def test_lean_symbol_and_vendor_version_must_match():
    sc = {"lean-guid-001": sidecar()}
    for symbol, version in (
        ("EURUSD", PINNED_VENDOR["lean"]), ("XAUUSD", "0" * 40)):
        with pytest.raises(ValueError):
            normalize_lean_closed_trades(
                lean(), sc, expected_sidecar_sha256=pinned(sc),
                source_symbol=symbol, vendor_commit=version)


def test_nautilus_reopened_snapshot_and_nonflat_refused():
    sc = {"P-001": sidecar()}
    for column, value in (("is_snapshot", True), ("side", "LONG"),
                          ("quantity", "1")):
        rows = nautilus()
        rows.at["P-001", column] = value
        with pytest.raises(ValueError):
            normalize_nautilus_positions_report(
                rows, sc, expected_sidecar_sha256=pinned(sc),
                instrument_id="XAUUSD.SIM",
                vendor_commit=PINNED_VENDOR["nautilus"])


def test_nautilus_non_usd_and_multiplier_mismatch_refused():
    sc = {"P-001": sidecar()}
    for column, value in (
        ("commissions", ["0.40 EUR"]),
        ("realized_pnl", "2.60 EUR"),
        ("peak_qty", "10"),
    ):
        rows = nautilus()
        rows.at["P-001", column] = value
        with pytest.raises(ValueError):
            normalize_nautilus_positions_report(
                rows, sc, expected_sidecar_sha256=pinned(sc),
                instrument_id="XAUUSD.SIM",
                vendor_commit=PINNED_VENDOR["nautilus"])


def test_source_and_sidecar_bijection_prevents_missing_trades():
    sc = {"lean-guid-001": sidecar()}
    with pytest.raises(ValueError, match="sidecars"):
        normalize_lean_closed_trades(
            lean(), {}, expected_sidecar_sha256=pinned({}),
            source_symbol="XAUUSD", vendor_commit=PINNED_VENDOR["lean"])
    wrong = {"lean-guid-001": dict(sidecar(), stop=1990)}
    with pytest.raises(ValueError, match="hash mismatch"):
        normalize_lean_closed_trades(
            lean(), wrong, expected_sidecar_sha256=pinned(sc),
            source_symbol="XAUUSD", vendor_commit=PINNED_VENDOR["lean"])


def test_missing_signal_metadata_is_never_guessed():
    source = lean()
    sc = {"lean-guid-001": dict(sidecar())}
    del sc["lean-guid-001"]["stop"]
    with pytest.raises(ValueError, match="source mapping"):
        normalize_lean_closed_trades(
            source, sc, expected_sidecar_sha256=pinned(sc),
            source_symbol="XAUUSD", vendor_commit=PINNED_VENDOR["lean"])


def test_closed_nautilus_order_quantity_zero_is_not_assumed_trade_size():
    sc = {"P-001": sidecar()}
    rows = nautilus()
    rows.at["P-001", "peak_qty"] = "0"
    with pytest.raises(ValueError):
        normalize_nautilus_positions_report(
            rows, sc, expected_sidecar_sha256=pinned(sc),
            instrument_id="XAUUSD.SIM",
            vendor_commit=PINNED_VENDOR["nautilus"])
