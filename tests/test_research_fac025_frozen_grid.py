"""FAC025 frozen-grid cardinality, deterministic identity and fail-closed tests."""
import copy
import pytest
from scripts.research_fac025_frozen_grid import (
    frozen_manifest, frozen_specs, validate_frozen_spec,
)


def test_exact_72_correlated_specs_not_72_hypotheses():
    specs = frozen_specs()
    assert len(specs) == len({s["fingerprint"] for s in specs}) == 72
    assert [s["id"] for s in specs] == [f"FAC025-{i:03d}" for i in range(1, 73)]
    assert len({tuple(s["parameters"].items()) for s in specs}) == 72
    assert {s["parameters"]["lookback"] for s in specs} == {4, 8, 12}
    assert {s["parameters"]["min_range_ratio"] for s in specs} == {"0.0004", "0.0008"}
    assert {s["parameters"]["max_range_ratio"] for s in specs} == {"0.003", "0.006"}
    assert {s["parameters"]["daily_loss_halt"] for s in specs} == {"2", "4", "6"}
    assert {(s["parameters"]["session_start_hour"], s["parameters"]["session_end_hour"])
            for s in specs} == {(8, 12), (9, 13)}
    assert frozen_manifest()["hypothesis_count"] == 1
    assert frozen_manifest()["grid_sha256"] == (
        "9646a2d037024f7a18bd97eca3187ccf6404e34f58c713e402c1c407fba3c702"
    )


def test_repeated_grid_is_deterministic_and_each_spec_roundtrips():
    assert frozen_specs() == frozen_specs()
    assert frozen_manifest() == frozen_manifest()
    for spec in frozen_specs():
        assert validate_frozen_spec(spec["parameters"], spec["fingerprint"]) == spec


@pytest.mark.parametrize("field,replacement", [
    ("lookback", 16), ("lookback", True), ("lookback", 4.0),
    ("min_range_ratio", "0.0005"), ("min_range_ratio", 0.0004),
    ("max_range_ratio", "0.009"), ("daily_loss_halt", "8"),
    ("session_start_hour", 7), ("session_end_hour", 14),
])
def test_unfrozen_grid_values_are_rejected(field, replacement):
    spec = frozen_specs()[0]
    params = copy.deepcopy(spec["parameters"])
    params[field] = replacement
    with pytest.raises(ValueError):
        validate_frozen_spec(params, spec["fingerprint"])


def test_tampered_digest_and_extra_fields_are_rejected():
    spec = frozen_specs()[0]
    with pytest.raises(ValueError, match="fingerprint"):
        validate_frozen_spec(spec["parameters"], "0" * 64)
    extra = {**spec["parameters"], "profitable_months": 12}
    with pytest.raises(ValueError, match="schema"):
        validate_frozen_spec(extra, spec["fingerprint"])
    reordered = dict(reversed(list(spec["parameters"].items())))
    with pytest.raises(ValueError, match="schema"):
        validate_frozen_spec(reordered, spec["fingerprint"])


def test_manifest_never_claims_backtest_or_approved_strategy():
    m = frozen_manifest()
    assert m["executed_original_source_backtests"] == 0
    assert m["monthly_pnl"] == m["floating_m1_drawdown"] == "N/A"
    assert m["entry_exit_defined"] is False
    assert m["shared_capacity_verified"] is False
