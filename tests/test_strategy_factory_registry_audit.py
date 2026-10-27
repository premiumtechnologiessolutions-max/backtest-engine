"""Synthetic accounting regressions; no original market quotes required."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.audit_strategy_factory_registry import (
    REGISTRY, RegistryAuditError, audit_registry,
)


def _registry():
    return json.loads(Path(REGISTRY).read_text(encoding="utf-8"))


def test_real_registry_reconciles_without_touching_private_quotes():
    result = audit_registry(_registry())
    assert result["distinct_parameter_specs"] == 305616
    assert result["independent_hypothesis_families"] == 13
    assert result["zero_trade_parameter_specs_excluded"] == 32088
    assert result["yearly_backtests"] == 587820
    assert result["exit_booked_monthly_points"] == 7053840
    assert result["total_yearly_parameter_executions_including_zero_trade_negative_control"] == 662532
    assert result["zero_trade_yearly_parameter_executions_excluded"] == 74712
    assert result["strictly_positive_every_month_in_both_years"] == 0


@pytest.mark.parametrize("change,match", [
    (lambda d: d["totals"].__setitem__("yearly_backtests", 999999), "yearly_backtests"),
    (lambda d: d["totals"].__setitem__("exit_booked_monthly_points", 999999), "exit_booked_monthly_points"),
    (lambda d: d["totals"].__setitem__("distinct_parameter_specs", 999999), "distinct_parameter_specs"),
    (lambda d: d["completed_batches"].append(deepcopy(d["completed_batches"][0])), "duplicate batch"),
    (lambda d: d["completed_batches"][1].__setitem__("file", d["completed_batches"][0]["file"]), "duplicate runner"),
    (lambda d: d["completed_batches"][0].__setitem__("completed_annual_replays", 40001), "annual executions"),
    (lambda d: d["completed_batches"][-1].__setitem__("active_annual_replays", 36000), "zero-trade reconciliation"),
    (lambda d: d["completed_batches"][-1].__setitem__("active_monthly_values", 432000), "active monthly"),
    (lambda d: d["completed_batches"][-1].__setitem__("configs_24_of_24", 1), "strictly_positive"),
    (lambda d: d["completed_batches"][0].__setitem__("years", [2013, 2012]), "design years"),
    (lambda d: d["feasibility_negative_controls"][0].__setitem__("active_annual_replays", 1), "negative control"),
    (lambda d: d.__setitem__("fixed_roundtrip_all_in_fee_usd_per_oz", 0.5), "roundtrip fee"),
    (lambda d: d.__setitem__("research_status", "CLEAN_OOS"), "relabeled OOS"),
    (lambda d: d.__setitem__("original_private_zip_sha256", "0"*64), "SHA256"),
])
def test_corrupted_registry_fails_closed(change, match):
    data = _registry()
    change(data)
    with pytest.raises(RegistryAuditError, match=match):
        audit_registry(data)


@pytest.mark.parametrize("bad", [True, 1.5, -1, None])
def test_invalid_counter_types_fail_closed(bad):
    data = _registry()
    data["totals"]["yearly_backtests"] = bad
    with pytest.raises(RegistryAuditError, match="nonnegative integer"):
        audit_registry(data)
