"""B08 integration: one source-aware operator view, without merged market data."""
from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from norisk_quant.research_control_plane import ResearchQueue, SCHEMA, EXTERNAL_SOURCE
from norisk_quant.source_registry import SourceRegistry, register_original_gold_m1
from norisk_quant.unified_research_platform import UnifiedResearchPlatform


def terminal_fixture():
    return {
        "data_kind": "broker_history", "frame": "M1",
        "contract": {
            "asset": "XAUUSD", "instrument": "XAUUSD-STDc",
            "provider": "VT Markets MT5 · Cent",
            "provider_scope": "e"*64, "account_currency": "USC",
            "quote_currency": "USD", "point_size": 0.01,
            "unit_step": 0.01, "minimum_units": 0.01,
        },
        "config": {
            "capital":10000, "risk_pct":0.1, "commission_per_side":0,
            "slippage_points":1, "latency_ms":250,
            "max_quote_gap_seconds":30, "max_hold_seconds":900,
        },
        "source_evidence": {
            "origin":"MT5 read-only terminal",
            "collector_version":"mt5_cent_history_v1",
            "account_kind":"real_cent_read_only",
            "commission_status":"unverified_zero_assumption",
            "denomination_factor":100,
        },
        "ticks": [
            {"at":"2026-10-29T09:00:00.111+00:00","seq":0,"bid":4021,"ask":4021.2,
             "quote_to_account":100,
             "conversion_source":"VT USC denomination / MT5 order_calc_profit cross-check"},
            {"at":"2026-10-29T09:00:00.115+00:00","seq":1,"bid":4021.05,"ask":4021.25,
             "quote_to_account":100,
             "conversion_source":"VT USC denomination / MT5 order_calc_profit cross-check"},
        ],
    }


def raw(value):
    return json.dumps(value,ensure_ascii=False,separators=(",", ":")).encode("utf-8")


def month_manifest():
    return register_original_gold_m1({
        "origin":"user_supplied_gold_m1_bidask",
        "source_file_sha256":"a"*64,
        "observed_slice_sha256":"b"*64,
        "rows":30000,
        "first_utc":"2012-01-02T23:00:00+00:00",
        "last_utc":"2012-01-31T23:59:00+00:00",
    }).internal_manifest()


def platform(tmp_path):
    return UnifiedResearchPlatform(
        queue=ResearchQueue(tmp_path/"private-queue.sqlite3"),
        sources=SourceRegistry(),
    )


def test_all_sources_share_one_registry_but_never_merge_feeds(tmp_path):
    system=platform(tmp_path)
    gold=system.index_declared_source_manifest(month_manifest())
    tick=system.observe_terminal_snapshot(raw(terminal_fixture()))
    view=system.operator_snapshot()
    assert gold["family"]=="original_gold_m1_bidask"
    assert tick["family"]=="private_terminal_bidask_ticks"
    assert tick["source_claim"]=="BROKER_HISTORY_DECLARED"
    assert view["data_hub"]["registered_metadata_sources"]==2
    assert {r["family"] for r in view["data_hub"]["sources"]}=={
        "original_gold_m1_bidask","private_terminal_bidask_ticks",
    }
    assert view["data_hub"]["persisted_source_registry"] is False
    assert view["data_hub"]["original_gold_source_file_verified_here"] is False
    assert view["execution"]["strategy_execution_requested"] is False
    assert view["execution"]["broker_fill_parity"] is False


def test_same_source_repeated_import_is_idempotent(tmp_path):
    system=platform(tmp_path)
    source=raw(terminal_fixture())
    one=system.observe_terminal_snapshot(source)
    two=system.observe_terminal_snapshot(source)
    assert one==two
    assert system.operator_snapshot()["data_hub"]["registered_metadata_sources"]==1


def test_account_and_private_quote_scope_are_not_in_operator_snapshot(tmp_path):
    system=platform(tmp_path)
    system.observe_terminal_snapshot(raw(terminal_fixture()))
    system.index_declared_source_manifest(month_manifest())
    displayed=json.dumps(system.operator_snapshot(),sort_keys=True)
    for secret in (
        "4021.2", "4021.05", "USC", "VT Markets",
        "provider_scope", "account_kind", "quote_to_account",
        "source_file_sha256", "observed_quote_sha256",
        "a"*64, "b"*64, "e"*64, "password", "order_send",
    ):
        assert secret not in displayed
    assert "profitability_verified" in displayed
    assert '"approved_for_live": false' in displayed


def test_operator_pause_visible_without_implicitly_resuming(tmp_path):
    system=platform(tmp_path)
    initial=system.operator_snapshot()
    assert initial["research_control"]["operator_paused"] is True
    assert initial["execution"]["canonical_runner"]=="OPERATOR_GATED_POSIX_ONLY"
    assert system.queue.counts()["paused"] is True


def test_queue_agent_cannot_change_operator_view_to_profitable(tmp_path):
    system=platform(tmp_path)
    proposal={
        "schema":SCHEMA,"producer":EXTERNAL_SOURCE,
        "agent":"nova","campaign_id":"campaign_b08","asset":"XAUUSD",
        "dataset_sha256":"a"*64,"engine_commit":"b"*40,
        "strategy_id":"aql_opaque_external_hash",
        "parameters":{"lookback":20},"timeframe":"M1",
        "window_start_utc":"2024-01-01T00:00:00Z",
        "window_end_exclusive_utc":"2024-02-01T00:00:00Z",
        "quantity_ounces":1.0,"fee_all_in_per_ounce":0.40,
        "execution_mode":"m1_conservative",
        "exposure_context":"historical_exposed",
    }
    system.queue.submit(proposal,now=datetime(2026,10,30,tzinfo=timezone.utc))
    view=system.operator_snapshot()
    assert view["research_control"]["counts"]["queued"]==1
    assert view["research_control"]["hypothesis_payloads_visible"] is False
    assert view["execution"]["profitability_verified"] is False
    assert "aql_opaque_external_hash" not in json.dumps(view)
    assert system.queue.counts()["paused"] is True


def test_unauthenticated_internal_source_records_cannot_self_certify(tmp_path):
    system=platform(tmp_path)
    m=month_manifest()
    m["record"]["source_authentication"]="BROKER_CERTIFIED"
    with pytest.raises(ValueError,match="identity mismatch"):
        system.index_declared_source_manifest(m)
    assert system.operator_snapshot()["data_hub"]["registered_metadata_sources"]==0


def test_no_live_tick_claim_accepted_at_platform_boundary(tmp_path):
    system=platform(tmp_path)
    request=terminal_fixture()
    request["results"]={"profit":999999,"live":True}
    with pytest.raises(ValueError,match="schema"):
        system.observe_terminal_snapshot(raw(request))
    assert system.operator_snapshot()["data_hub"]["registered_metadata_sources"]==0


def test_wrong_constructor_inputs_fail_without_side_effect(tmp_path):
    with pytest.raises(TypeError):
        UnifiedResearchPlatform(queue=object())
    with pytest.raises(TypeError):
        UnifiedResearchPlatform(queue=ResearchQueue(tmp_path/"q.sqlite3"),sources={})


def test_view_has_explicit_missing_proof_and_no_executable_orders(tmp_path):
    view=platform(tmp_path).operator_snapshot()
    assert view["review_gates"]["market_gap_calendar_review"]=="REQUIRED"
    assert view["review_gates"]["private_operator_authentication"]=="NOT_IMPLEMENTED_BY_THIS_VIEW"
    assert view["execution"]["mt5_order_connection"] is False
    assert view["execution"]["oracle_deployment"] is False
    assert view["execution"]["independent_oos"] is False
    assert view["research_control"]["agent_authorized_to_certify_profit"] is False
