"""End-to-end B01->B02: exact local private quote input to safe metadata."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from norisk_quant.integrations.unified_source_intake import (
    ingest_terminal_snapshot, inspect_local_file,
)


def sample(*, kind="broker_history"):
    return {
        "data_kind": kind,
        "frame": "M1",
        "contract": {
            "asset": "XAUUSD", "instrument": "XAUUSD-STDc",
            "provider": "VT Markets MT5 · Cent",
            "provider_scope": "e" * 64, "account_currency": "USC",
            "quote_currency": "USD", "point_size": 0.01,
            "unit_step": 0.01, "minimum_units": 0.01,
        },
        "config": {
            "capital": 10000, "risk_pct": 0.1, "commission_per_side": 0,
            "slippage_points": 1, "latency_ms": 250,
            "max_quote_gap_seconds": 30, "max_hold_seconds": 900,
        },
        "source_evidence": {
            "origin": "MT5 read-only terminal",
            "collector_version": "mt5_cent_history_v1",
            "account_kind": "real_cent_read_only",
            "commission_status": "unverified_zero_assumption",
            "denomination_factor": 100,
        },
        "ticks": [
            {"at": "2026-10-29T09:00:00.111+00:00", "seq": 0, "bid": 4021.00, "ask": 4021.20,
             "quote_to_account": 100,
             "conversion_source": "VT USC denomination / MT5 order_calc_profit cross-check"},
            {"at": "2026-10-29T09:00:00.115+00:00", "seq": 1, "bid": 4021.05, "ask": 4021.25,
             "quote_to_account": 100,
             "conversion_source": "VT USC denomination / MT5 order_calc_profit cross-check"},
            {"at": "2026-10-29T09:00:00.129+00:00", "seq": 2, "bid": 4020.99, "ask": 4021.19,
             "quote_to_account": 100,
             "conversion_source": "VT USC denomination / MT5 order_calc_profit cross-check"},
        ],
    }


def pack(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=True, separators=(",", ":")).encode("utf-8")


def test_real_v0191_contract_full_pipeline_no_execution_or_fees():
    source = sample()
    x = ingest_terminal_snapshot(pack(source))
    assert x.record.asset == "XAUUSD"
    assert x.record.instrument == "XAUUSD-STDc"
    assert x.record.source_claim == "BROKER_HISTORY_DECLARED"
    assert x.record.account_currency == "USC"
    assert x.record.quote_currency == "USD"
    assert len(x.ticks) == x.record.rows == 3
    assert list(x.ticks["bid"]) == [4021.00, 4021.05, 4020.99]
    assert list(x.ticks["quote_to_account"]) == [100.0] * 3
    assert x.record.cost_policy == "NO_COST_AT_DATA_LAYER"
    assert x.record.source_authentication == "NOT_VERIFIED"
    assert x.record.execution == "NONE"
    assert x.record.independent_oos is False


def test_records_change_only_when_source_data_or_contract_changes():
    a = sample()
    b = sample()
    b["ticks"][0]["bid"] += 0.01
    assert ingest_terminal_snapshot(pack(a)).record.id != ingest_terminal_snapshot(pack(b)).record.id
    c = sample()
    c["contract"]["provider_scope"] = "f" * 64
    assert ingest_terminal_snapshot(pack(a)).record.id != ingest_terminal_snapshot(pack(c)).record.id


def test_private_scope_not_visible_in_public_metadata():
    x = ingest_terminal_snapshot(pack(sample()))
    summary = x.public_metadata()
    assert summary["family"] == "private_terminal_bidask_ticks"
    assert summary["source_claim"] == "BROKER_HISTORY_DECLARED"
    assert "quote_context_sha256" not in summary
    assert "provider_scope" not in str(summary)
    assert "e" * 64 not in str(summary)
    assert "4021" not in str(summary)
    assert "USC" not in str(summary)


def test_private_file_preflight_returns_safe_summary(tmp_path):
    path = tmp_path / "private-gold.json"
    path.write_bytes(pack(sample()))
    out = inspect_local_file(path)
    assert out["data_hub"]["rows"] == 3
    assert out["audit"]["fees"] == "NOT_APPLIED"
    assert out["audit"]["real_trading"] is False
    assert out["audit"]["broker_fill_parity"] is False
    assert out["audit"]["profitability_verified"] is False
    assert "4021" not in json.dumps(out)
    assert "e" * 64 not in json.dumps(out)


def test_cli_does_not_print_source_private_scope_quote_or_account(tmp_path, capsys):
    from scripts.verify_unified_source_intake import main
    path = tmp_path / "private-request.json"
    path.write_bytes(pack(sample()))
    assert main([str(path)]) == 0
    printed = capsys.readouterr().out
    assert "manifest_id" in printed
    assert "cost_model" in printed
    assert "BROKER_HISTORY_DECLARED" in printed
    assert "4021" not in printed
    assert "e" * 64 not in printed
    assert "USC" not in printed
    assert "password" not in printed


def test_pseudo_live_signal_is_rejected_not_promoted():
    payload = sample()
    payload["results"] = [{"trade": "LIVE", "pnl": 9999}]
    with pytest.raises(ValueError, match="schema"):
        ingest_terminal_snapshot(pack(payload))


def test_synthetic_is_explicitly_rejected_or_labeled():
    payload = sample(kind="synthetic_test")
    payload["contract"]["provider_scope"] = "synthetic-local-only"
    with pytest.raises(ValueError, match="explicit opt in"):
        ingest_terminal_snapshot(pack(payload))
    a = ingest_terminal_snapshot(pack(payload), allow_synthetic=True)
    assert a.record.source_claim == "SYNTHETIC"
    assert a.record.execution == "NONE"
    assert a.record.source_authentication == "NOT_VERIFIED"


@pytest.mark.parametrize("field,edited", [
    ("bid", 4100), ("ask", 3900), ("seq", True),
    ("quote_to_account", 1), ("at", "2026-10-29T12:00:00+03:00"),
])
def test_invalid_private_tick_rejected(field, edited):
    request = sample()
    request["ticks"][0][field] = edited
    with pytest.raises(ValueError):
        ingest_terminal_snapshot(pack(request))


def test_source_file_regular_non_symlink_and_size_gates(tmp_path):
    real = tmp_path / "real.json"
    real.write_bytes(pack(sample()))
    link = tmp_path / "link.json"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink not available on this filesystem")
    with pytest.raises(ValueError, match="non-symlink"):
        inspect_local_file(link)
    empty = tmp_path / "empty.json"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        inspect_local_file(empty)


def test_cli_bad_metadata_no_private_value_or_source_bytes_in_error(tmp_path, capsys):
    from scripts.verify_unified_source_intake import main
    request = sample()
    request["password"] = "topsecret-value"
    file = tmp_path / "untrusted.json"
    file.write_bytes(pack(request))
    with pytest.raises(SystemExit) as end:
        main([str(file)])
    assert end.value.code == 2
    output = capsys.readouterr().err
    assert "topsecret-value" not in output
    assert "provider_scope" not in output


def test_no_automatic_mutation_of_original_source(tmp_path):
    before = pack(sample())
    path = tmp_path / "readonly-input.json"
    path.write_bytes(before)
    inspect_local_file(path)
    assert path.read_bytes() == before


def test_ordered_utc_ticks_preserved_without_missing_fabrication():
    source = sample()
    source["ticks"][2]["at"] = "2026-10-29T09:01:30.129+00:00"
    result = ingest_terminal_snapshot(pack(source))
    assert result.record.rows == 3
    assert len(result.ticks) == 3
    assert result.ticks.index[-1].minute == 1
    assert result.ticks.index[-1].second == 30
