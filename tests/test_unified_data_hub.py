"""NoRiskFX Data Hub cross-system metadata, privacy and no-merging gates."""
from __future__ import annotations

from dataclasses import replace
from copy import deepcopy

import pytest

from norisk_quant.source_registry import (
    SCHEMA, SourceRecord, SourceRegistry, compare_source_windows,
    register_original_gold_m1, register_terminal_tick_evidence,
    verify_record_manifest,
)


def gold_meta():
    return {
        "origin": "user_supplied_gold_m1_bidask",
        "source_file_sha256": "a" * 64,
        "observed_slice_sha256": "b" * 64,
        "rows": 150000,
        "first_utc": "2025-01-01T00:00:00Z",
        "last_utc": "2025-12-30T23:59:00Z",
    }


def terminal_meta():
    return {
        "schema_version": "noriskfx-terminal-tick-import-v1",
        "source_bytes_sha256": "c" * 64,
        "quote_context_sha256": "d" * 64,
        "provider_declared": "VT Markets MT5 · Cent",
        "symbol_declared": "XAUUSD-STDc",
        "source_kind_declared": "broker_history",
        "source_authentication": "NOT_VERIFIED",
        "account_currency_label": "USC",
        "quote_currency_label": "USD",
        "ticks": 110208,
        "first_utc": "2026-10-29T09:00:00.000000+00:00",
        "last_utc": "2026-10-29T14:59:59.999000+00:00",
        "cost_model": "NOT_APPLIED_DATA_ONLY",
        "execution": "NONE_RESEARCH_IMPORT",
        "simulation_results_imported": False,
        "independent_oos": False,
        "broker_fill_parity": False,
        "notice": "Declared broker quotes are not authenticated fills; source simulation fees are not transferred.",
    }


def test_original_m1_metadata_has_no_tick_or_authentication_claim():
    row = register_original_gold_m1(gold_meta())
    assert row.family == "original_gold_m1_bidask"
    assert row.source_claim == "ORIGINAL_M1_DECLARED"
    assert row.instrument == "XAUUSD"
    assert row.account_currency is None
    assert row.execution == "NONE"
    assert row.cost_policy == "NO_COST_AT_DATA_LAYER"
    assert row.source_authentication == "NOT_VERIFIED"
    assert not row.independent_oos
    assert row.data_rights == "UNVERIFIED"
    assert len(row.id) == 64
    assert verify_record_manifest(row.internal_manifest()) == row


def test_terminal_usc_scope_and_quote_fingerprints_remain_separate():
    item = register_terminal_tick_evidence(terminal_meta())
    assert item.family == "private_terminal_bidask_ticks"
    assert item.source_claim == "BROKER_HISTORY_DECLARED"
    assert item.asset == "XAUUSD"
    assert item.account_currency == "USC"
    assert item.quote_currency == "USD"
    assert item.rows == 110208
    assert item.source_file_sha256 != item.observed_quote_sha256
    assert item.access == "PRIVATE_LOCAL_ONLY"
    assert not item.independent_oos
    assert item.execution == "NONE"


def test_replayable_identity_is_stable_across_normalized_utc_formats():
    left = gold_meta()
    right = gold_meta()
    right["first_utc"] = "2025-01-01T00:00:00+00:00"
    assert register_original_gold_m1(left).id == register_original_gold_m1(right).id


def test_public_summary_excludes_raw_fingerprints_and_broker_scope():
    row = register_terminal_tick_evidence(terminal_meta())
    public = row.public_summary()
    assert public["schema"] == SCHEMA
    assert "source_file_sha256" not in public
    assert "observed_quote_sha256" not in public
    assert "provider_declared" not in public
    assert "account_currency" not in public
    assert "quote_context_sha256" not in public
    assert "source_authentication" in public
    assert public["execution"] == "NONE"


def test_registry_is_idempotent_and_sorts_summaries():
    collection = SourceRegistry()
    row = register_terminal_tick_evidence(terminal_meta())
    other = register_original_gold_m1(gold_meta())
    assert collection.add(row) == row.id
    assert collection.add(row) == row.id
    collection.add(other)
    assert len(collection.summaries()) == 2
    assert {r["manifest_id"] for r in collection.summaries()} == {row.id, other.id}
    assert collection.get(row.id) == row


def test_same_feed_changed_data_hash_changes_manifest():
    one = terminal_meta()
    two = deepcopy(one)
    two["quote_context_sha256"] = "f" * 64
    assert register_terminal_tick_evidence(one).id != register_terminal_tick_evidence(two).id


def test_same_feed_changed_account_currency_changes_manifest():
    one = terminal_meta()
    two = deepcopy(one)
    two["account_currency_label"] = "USD"
    assert register_terminal_tick_evidence(one).id != register_terminal_tick_evidence(two).id


@pytest.mark.parametrize("key,bad,match", [
    ("source_authentication", "VERIFIED", "Untrusted Terminal"),
    ("cost_model", "PAID_BROKER_FILL", "Untrusted Terminal"),
    ("execution", "LIVE", "Untrusted Terminal"),
    ("simulation_results_imported", True, "Untrusted Terminal"),
    ("independent_oos", True, "Untrusted Terminal"),
    ("broker_fill_parity", True, "Untrusted Terminal"),
    ("ticks", True, "row count"),
    ("ticks", 0, "row count"),
    ("ticks", 1, "two tick"),
    ("ticks", float("nan"), "row count"),
    ("source_bytes_sha256", "x" * 64, "source_file_sha256"),
    ("quote_context_sha256", "x" * 64, "observed_quote_sha256"),
    ("first_utc", "2026-10-29T12:00:00+03:00", "UTC"),
    ("last_utc", "2026-10-29T15:00:00", "UTC"),
    ("last_utc", "2026-10-28T12:00:00Z", "interval"),
    ("account_currency_label", "USD01", "account_currency"),
    ("quote_currency_label", "EUR", "Quote currency"),
    ("symbol_declared", "USDJPY-STDc", "Quote currency"),
    ("symbol_declared", "XAUUSD-STDc hacked", "symbol_declared"),
])
def test_broker_metadata_fails_closed(key, bad, match):
    item = terminal_meta()
    item[key] = bad
    with pytest.raises(ValueError, match=match):
        register_terminal_tick_evidence(item)


def test_no_extra_scope_account_or_credentials_in_terminal_evidence():
    for addition in ("account_id", "provider_scope", "login", "password", "profit"):
        item = terminal_meta()
        item[addition] = "private"
        with pytest.raises(ValueError, match="schema"):
            register_terminal_tick_evidence(item)


def test_no_synthetic_unless_opted_in():
    item = terminal_meta()
    item["source_kind_declared"] = "synthetic_test"
    with pytest.raises(ValueError, match="Synthetic"):
        register_terminal_tick_evidence(item)
    row = register_terminal_tick_evidence(item, permit_synthetic=True)
    # The source remains UNVERIFIED; synthetic opt-in is never evidence of broker execution.
    assert row.source_authentication == "NOT_VERIFIED"
    assert row.execution == "NONE"
    assert row.source_claim == "SYNTHETIC"


def test_m1_prevents_timestamp_with_seconds_and_invalid_origin():
    m = gold_meta()
    m["first_utc"] = "2025-01-01T00:00:01Z"
    with pytest.raises(ValueError, match="minute opens"):
        register_original_gold_m1(m)
    m = gold_meta()
    m["origin"] = "private_tick_feed"
    with pytest.raises(ValueError, match="origin"):
        register_original_gold_m1(m)


def test_original_m1_source_must_not_have_private_scope_fields():
    m = gold_meta()
    m["account_scope"] = "do-not-leak"
    with pytest.raises(ValueError, match="missing or extra keys"):
        register_original_gold_m1(m)


def test_original_m1_price_dates_and_hash_changes_affect_identity():
    m = gold_meta()
    record = register_original_gold_m1(m)
    m["source_file_sha256"] = "e" * 64
    assert record.id != register_original_gold_m1(m).id


def test_manifest_tampering_fails_digest_and_status_gate():
    record = register_terminal_tick_evidence(terminal_meta())
    good = record.internal_manifest()
    assert verify_record_manifest(good) == record
    for key, bad in (
        ("rows", 5), ("source_authentication", "VERIFIED"),
        ("cost_policy", "FREE_TRADES"), ("independent_oos", True),
        ("execution", "LIVE"), ("access", "PUBLIC"),
    ):
        changed = deepcopy(good)
        changed["record"][key] = bad
        with pytest.raises(ValueError, match="identity mismatch"):
            verify_record_manifest(changed)


def test_manual_constructed_record_cannot_bypass_registry_checks():
    real = register_terminal_tick_evidence(terminal_meta())
    unsafe = replace(real, source_authentication="VERIFIED")
    with pytest.raises(ValueError, match="identity mismatch"):
        SourceRegistry().add(unsafe)


def test_bad_manifest_ids_and_extra_fields_are_rejected():
    record = register_original_gold_m1(gold_meta())
    m = record.internal_manifest()
    m["extra"] = "source leak"
    with pytest.raises(ValueError, match="envelope"):
        verify_record_manifest(m)
    m = record.internal_manifest()
    m["id"] = "abc"
    with pytest.raises(ValueError, match="manifest id"):
        verify_record_manifest(m)


def test_comparison_does_not_merge_original_m1_and_private_tick_snapshot():
    a = register_original_gold_m1(gold_meta())
    b = register_terminal_tick_evidence(terminal_meta())
    info = compare_source_windows(a, b)
    assert info["same_asset"] is True
    assert info["can_merge_as_one_market_feed"] is False
    assert info["can_establish_broker_fill_parity"] is False
    assert info["can_compare_quote_observations"] is False  # Years do not overlap


def test_overlapping_sources_can_compare_only_not_merge():
    m = gold_meta()
    m["first_utc"] = "2026-10-29T09:00:00Z"
    m["last_utc"] = "2026-10-29T15:00:00Z"
    a = register_original_gold_m1(m)
    b = register_terminal_tick_evidence(terminal_meta())
    info = compare_source_windows(a, b)
    assert info["time_intersection"] is True
    assert info["can_compare_quote_observations"] is True
    assert info["can_merge_as_one_market_feed"] is False
    assert info["can_establish_broker_fill_parity"] is False


def test_unrelated_asset_cannot_claim_comparable_quote_observation():
    m = terminal_meta()
    m["symbol_declared"] = "EURUSD-STDc"
    m["quote_currency_label"] = "USD"
    b = register_terminal_tick_evidence(m)
    a = register_original_gold_m1(gold_meta())
    assert compare_source_windows(a, b)["same_asset"] is False


def test_evidence_does_not_contain_raw_market_ticks_or_trading_approval():
    item = terminal_meta()
    item["ticks"] = [{"bid": 4000.1, "ask": 4000.3}]
    with pytest.raises(ValueError, match="row count"):
        register_terminal_tick_evidence(item)


def test_disallowed_arbitrary_source_family_even_with_recomputed_hash():
    record = register_original_gold_m1(gold_meta())
    manifest = record.internal_manifest()
    manifest["record"]["family"] = "AUTHENTICATED_LIVE_TRADES"
    # A valid 64-digit ID is insufficient without matching immutable payload.
    with pytest.raises(ValueError):
        verify_record_manifest(manifest)
