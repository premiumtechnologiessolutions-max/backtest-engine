"""Cross-repository contract tests: Terminal v0.19.1 -> canonical quote intake."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from norisk_quant.integrations.terminal_ticks import import_terminal_ticks


def fixture(*, kind="broker_history", account="USC"):
    return {
        "data_kind": kind,
        "frame": "M1",
        "contract": {
            "asset": "XAUUSD", "instrument": "XAUUSD-STDc", "provider": "VT Markets MT5 · Cent",
            "provider_scope": "a" * 64, "account_currency": account,
            "quote_currency": "USD", "point_size": 0.01,
            "unit_step": 0.01, "minimum_units": 0.01,
        },
        "config": {"capital": 10000, "risk_pct": 0.1, "commission_per_side": 0,
                   "slippage_points": 1, "latency_ms": 250, "max_quote_gap_seconds": 30,
                   "max_hold_seconds": 900},
        "source_evidence": {"origin": "MT5 read-only terminal", "collector_version": "mt5_cent_history_v1",
                            "account_kind": "real_cent_read_only", "denomination_factor": 100,
                            "commission_status": "unverified_zero_assumption"},
        "ticks": [
            {"at": "2026-10-29T12:01:00.123+00:00", "seq": 0, "bid": 4010.10,
             "ask": 4010.20, "quote_to_account": 100,
             "conversion_source": "VT USC denomination / MT5 order_calc_profit cross-check"},
            {"at": "2026-10-29T12:01:00.123+00:00", "seq": 1, "bid": 4010.15,
             "ask": 4010.25, "quote_to_account": 100,
             "conversion_source": "VT USC denomination / MT5 order_calc_profit cross-check"},
            {"at": "2026-10-29T12:01:01.002+00:00", "seq": 2, "bid": 4010.18,
             "ask": 4010.28, "quote_to_account": 100,
             "conversion_source": "VT USC denomination / MT5 order_calc_profit cross-check"},
        ],
    }


def encoded(data):
    return json.dumps(data, ensure_ascii=False, allow_nan=True).encode("utf-8")


def test_import_preserves_ticks_and_usc_denomination_without_applying_fee():
    result = import_terminal_ticks(encoded(fixture()))
    assert len(result.ticks) == 3
    assert list(result.ticks["seq"]) == [0, 1, 2]
    assert list(result.ticks["quote_to_account"]) == [100, 100, 100]
    assert result.ticks["bid"].iloc[0] == 4010.10
    assert str(result.ticks.index.tz) == "UTC"
    assert result.evidence["cost_model"] == "NOT_APPLIED_DATA_ONLY"
    assert result.evidence["source_authentication"] == "NOT_VERIFIED"
    assert not result.evidence["simulation_results_imported"]
    assert not result.evidence["broker_fill_parity"]
    assert result.source.source_kind == "declared_broker_ticks"
    assert "provider_scope" not in str(result.evidence)


def test_exact_bytes_change_but_normalized_ticks_identity_is_stable():
    a = encoded(fixture())
    b = json.dumps(fixture(), ensure_ascii=False, indent=2).encode("utf-8")
    left = import_terminal_ticks(a).evidence
    right = import_terminal_ticks(b).evidence
    assert left["source_bytes_sha256"] != right["source_bytes_sha256"]
    assert left["quote_context_sha256"] == right["quote_context_sha256"]


def test_broker_scope_changes_quote_fingerprint_without_leaking_raw_scope():
    first = fixture()
    second = fixture()
    second["contract"]["provider_scope"] = "b" * 64
    left = import_terminal_ticks(encoded(first)).evidence
    right = import_terminal_ticks(encoded(second)).evidence
    assert left["quote_context_sha256"] != right["quote_context_sha256"]
    assert "a" * 64 not in str(left)
    assert "b" * 64 not in str(right)


def test_quote_change_changes_fingerprint():
    first = fixture()
    second = deepcopy(first)
    second["ticks"][0]["bid"] += 0.01
    assert import_terminal_ticks(encoded(first)).evidence["quote_context_sha256"] != import_terminal_ticks(encoded(second)).evidence["quote_context_sha256"]


def test_synthetic_requires_opt_in_and_is_not_mislabeled_broker():
    data = fixture(kind="synthetic_test")
    data["contract"]["provider_scope"] = "isolated-test"
    with pytest.raises(ValueError, match="explicit opt in"):
        import_terminal_ticks(encoded(data))
    result = import_terminal_ticks(encoded(data), allow_synthetic=True)
    assert result.source.source_kind == "synthetic"
    assert result.evidence["source_kind_declared"] == "synthetic_test"
    assert not result.evidence["broker_fill_parity"]


@pytest.mark.parametrize("mutator,issue", [
    (lambda d: d.update(password="secret"), "schema"),
    (lambda d: d["contract"].update(login=12345), "schema"),
    (lambda d: d["source_evidence"].update(password="secret"), "schema"),
    (lambda d: d["ticks"][1].update(order_id=123), "schema"),
    (lambda d: d["contract"].update(provider_scope="12345"), "scope"),
    (lambda d: d["contract"].update(quote_currency="EUR"), "Quote currency"),
    (lambda d: d["ticks"][0].update(seq=True), "sequence"),
    (lambda d: d["ticks"][1].update(seq=0), "sequence"),
    (lambda d: d["ticks"][1].update(at="2026-10-29T11:59:59Z"), "backwards"),
    (lambda d: d["ticks"][1].update(at="2026-10-29T15:01:00+03:00"), "UTC"),
    (lambda d: d["ticks"][1].update(at="2026-10-29T12:01:00"), "UTC"),
    (lambda d: d["ticks"][1].update(bid=4010.35), "Crossed"),
    (lambda d: d["ticks"][1].update(ask=float("inf")), "non-finite"),
    (lambda d: d["ticks"][1].update(bid=float("nan")), "non-finite"),
    (lambda d: d["ticks"][1].pop("quote_to_account"), "quote_to_account"),
    (lambda d: d["ticks"][1].pop("conversion_source"), "conversion"),
    (lambda d: d["config"].update(risk_pct=3), "Out-of-bound"),
    (lambda d: d.update(data_kind="live_orders"), "dataset kind"),
])
def test_quarantine_malformed_or_untrusted_terminal_snapshot(mutator, issue):
    data = fixture()
    mutator(data)
    with pytest.raises(ValueError, match=issue):
        import_terminal_ticks(encoded(data))


def test_json_duplicate_keys_and_nonfinite_constants_rejected():
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        import_terminal_ticks(b'{"data_kind":"broker_history","data_kind":"synthetic_test"}')
    with pytest.raises(ValueError, match="non-finite"):
        import_terminal_ticks(b'{"price":NaN}')


def test_empty_and_nonbytes_rejected():
    for payload in (b"", "hello", None):
        with pytest.raises(ValueError):
            import_terminal_ticks(payload)


def test_direct_quote_currency_does_not_need_conversion_source():
    data = fixture(account="USD")
    for tick in data["ticks"]:
        tick.pop("conversion_source")
        tick["quote_to_account"] = 1
    output = import_terminal_ticks(encoded(data))
    assert set(output.ticks["quote_to_account"]) == {1}


def test_does_not_accept_a_completed_terminal_strategy_run_as_market_feed():
    data = fixture()
    data["results"] = [{"net_closed_account": 100000}]
    with pytest.raises(ValueError, match="schema"):
        import_terminal_ticks(encoded(data))


def test_private_cli_emits_only_evidence_without_data_or_scope(tmp_path, capsys):
    from scripts.verify_terminal_intake import main
    sample = tmp_path / "local-broker-history.json"
    sample.write_bytes(encoded(fixture()))
    assert main([str(sample)]) == 0
    report = capsys.readouterr().out
    assert "quote_context_sha256" in report
    assert "4010.10" not in report
    assert "a" * 64 not in report
    assert "account_kind" not in report
    assert "approved_for_live" not in report


def test_private_cli_rejects_untrusted_source(tmp_path):
    from scripts.verify_terminal_intake import main
    sample = tmp_path / "unsafe.json"
    data = fixture()
    data["password"] = "not-allowed"
    sample.write_bytes(encoded(data))
    with pytest.raises(SystemExit) as exc:
        main([str(sample)])
    assert exc.value.code == 2


@pytest.mark.parametrize("case", ["changed_tick", "changed_declared_factor", "missing_claim", "nonfinite_declared_factor"])
def test_vt_cent_denomination_cannot_be_spoofed(case):
    row = fixture()
    if case == "changed_tick":
        row["ticks"][1]["quote_to_account"] = 1
    elif case == "changed_declared_factor":
        row["source_evidence"]["denomination_factor"] = 1
        for tick in row["ticks"]:
            tick["quote_to_account"] = 1
    elif case == "missing_claim":
        row["source_evidence"].pop("account_kind")
    else:
        row["source_evidence"]["denomination_factor"] = float("inf")
    with pytest.raises(ValueError, match="USC|Cent|denomination|non-finite"):
        import_terminal_ticks(encoded(row))
