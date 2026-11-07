"""Cross-engine parity over synthetic trade rows; no vendor engine execution."""
import copy

import pandas as pd
import pytest

from norisk_quant.campaign_blueprint import freeze_blueprint
from norisk_quant.cross_engine_parity import compare_frozen_engine_ledgers


def blueprint():
    return freeze_blueprint({
        "source_commit": "a" * 40,
        "dataset": {"id": "xauusd_m1", "archive_sha256": "b" * 64,
                    "start": "2024-01-01", "end": "2024-12-31",
                    "format": "M1_BID_ASK_ORIGINAL"},
        "evaluation": {"start": "2024-01-01", "end": "2024-01-31",
                       "scope": "UNEXECUTED_RESEARCH_DESIGN"},
        "strategies": [{"id": "bos_fib", "code_sha256": "c" * 64,
                        "spec_sha256": "d" * 64}],
        "execution_engines": ["nautilus", "norisk_quant", "lean"],
        "ai_reviewers": [],
        "resource_limits": {"max_workers": 2, "max_ram_mb": 4096,
                            "max_disk_mb": 2048, "max_runtime_minutes": 120},
        "all_in_cost_usd_per_ounce": 0.4,
        "owner_policy": "ENGINE_CONSTRUCTION_ONLY_NO_EXECUTION",
    })


def trades():
    return pd.DataFrame([{
        "trade_id": "bos_fib_001", "strategy": "bos_fib",
        "signal_at": "2024-01-05T10:00:00Z",
        "entry_at": "2024-01-05T10:01:00Z",
        "closed_at": "2024-01-05T10:05:00Z",
        "side": 1, "entry_price": 2000.0, "exit_price": 2003.0,
        "stop": 1995.0, "target": 2005.0, "ounces": 1.0,
        "gross_pnl": 3.0, "cost": 0.4, "net_pnl": 2.6,
        "exit_reason": "time_exit", "gap_minutes": 0,
    }])


def engines():
    return {"norisk_quant": trades(),
            "nautilus": trades(),
            "lean": trades()}


def test_all_matching_rows_remain_unverified_and_unaccepted():
    report = compare_frozen_engine_ledgers(blueprint(), engines())
    assert report["status"] == "ROW_PARITY_MATCH_UNVERIFIED"
    assert report["reference_trade_count"] == 1
    assert report["field_discrepancy_count"] == 0
    assert report["fully_matching_reference_trades"] == {"lean": 1, "nautilus": 1}
    assert report["strategy_research_accepted"] is False
    assert report["upstream_engine_execution_attested"] is False
    assert report["worker_started"] is False


def test_identical_total_profit_can_hide_different_execution_prices():
    data = engines()
    data["lean"].loc[0, ["entry_price", "exit_price", "stop", "target"]] += 2.0
    report = compare_frozen_engine_ledgers(blueprint(), data)
    assert report["status"] == "ROW_PARITY_DISAGREEMENT_UNVERIFIED"
    assert report["field_discrepancy_count"] == 4
    assert {r["field"] for r in report["discrepancies"]} == {
        "entry_price", "exit_price", "stop", "target"}
    assert "2002" not in str(report["discrepancies"])


def test_missing_and_extra_trades_not_filtered_out():
    data = engines()
    data["lean"] = trades().iloc[:0].copy()
    data["nautilus"].loc[0, "trade_id"] = "different_001"
    report = compare_frozen_engine_ledgers(blueprint(), data)
    assert report["field_discrepancy_count"] == 3
    assert all(x["field"] == "presence" for x in report["discrepancies"])
    assert report["fully_matching_reference_trades"]["lean"] == 0


def test_no_trades_cannot_prove_simulators_were_run():
    data = {key: frame.iloc[:0].copy() for key, frame in engines().items()}
    report = compare_frozen_engine_ledgers(blueprint(), data)
    assert report["status"] == "NO_TRADES_UNVERIFIED"
    assert report["quote_source_provenance_verified"] is False


def test_missing_planned_engine_rejected_without_best_comparator_selection():
    data = engines()
    del data["nautilus"]
    with pytest.raises(ValueError, match="All frozen engines"):
        compare_frozen_engine_ledgers(blueprint(), data)
    data = engines()
    data["unknown"] = trades()
    with pytest.raises(ValueError, match="All frozen engines"):
        compare_frozen_engine_ledgers(blueprint(), data)


def test_corrupted_but_balancing_trade_rejected():
    data = engines()
    data["lean"].loc[0, "net_pnl"] = 10.0
    with pytest.raises(ValueError, match="accounting mismatch"):
        compare_frozen_engine_ledgers(blueprint(), data)


@pytest.mark.parametrize("field,value", [
    ("entry_price", "2000.0"),
    ("ounces", True),
    ("cost", float("nan")),
    ("net_pnl", float("inf")),
    ("side", True),
])
def test_noncanonical_fields_refused(field, value):
    data = engines()
    data["lean"].loc[0, field] = value
    with pytest.raises(ValueError):
        compare_frozen_engine_ledgers(blueprint(), data)


def test_naive_timestamp_and_duplicate_trade_ids_rejected():
    data = engines()
    data["lean"].loc[0, "entry_at"] = "2024-01-05T10:01:00"
    with pytest.raises(ValueError, match="timestamp"):
        compare_frozen_engine_ledgers(blueprint(), data)
    data = engines()
    data["lean"] = pd.concat([trades(), trades()], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate or unregistered"):
        compare_frozen_engine_ledgers(blueprint(), data)


def test_reversed_trade_chronology_rejected():
    data = engines()
    data["lean"].loc[0, "entry_at"] = "2024-01-05T10:10:00Z"
    with pytest.raises(ValueError, match="chronology"):
        compare_frozen_engine_ledgers(blueprint(), data)


def test_tampered_blueprint_cannot_enable_execution():
    frozen = blueprint()
    frozen["dag"][0]["execution_enabled"] = True
    with pytest.raises(ValueError):
        compare_frozen_engine_ledgers(frozen, engines())


def test_differences_report_is_bounded_and_hash_deterministic():
    frozen = blueprint()
    original = compare_frozen_engine_ledgers(frozen, engines())
    copied = {k: v.copy() for k, v in engines().items()}
    reordered = {k: copied[k] for k in reversed(copied)}
    assert compare_frozen_engine_ledgers(frozen, reordered) == original
    copied = engines()
    copied["lean"].loc[0, ["entry_price", "exit_price", "stop", "target"]] += 2.0
    out = compare_frozen_engine_ledgers(frozen, copied, max_differences=1)
    assert out["field_discrepancy_count"] == 4
    assert len(out["discrepancies"]) == 1
    assert out["discrepancies_truncated"] is True
