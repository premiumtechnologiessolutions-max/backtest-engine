"""Fail-closed arithmetic audit of the PUBLIC strategy-factory research registry.

No market quotes, trades or local private source are read. This checks that
reported experiment counts are internally consistent; it does not certify
execution, independence, profitability, or original-source replay parity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REGISTRY = Path(__file__).resolve().parents[1] / "research" / "strategy_factory_registry.json"
ORIGINAL_SHA256 = "1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121"


class RegistryAuditError(ValueError):
    """The public registry fails a research-accounting invariant."""


def _integer(value, label: str) -> int:
    if type(value) is not int or value < 0:
        raise RegistryAuditError(f"{label} must be a nonnegative integer")
    return value


def _assert_equal(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise RegistryAuditError(f"{label}: recomputed {actual}, registry {expected}")


def audit_registry(registry: dict) -> dict:
    """Recompute totals from executed annual replays, excluding zero-trade runs.

    FAC005 is an all-zero negative control. FAC012-A is a separate one-year
    feasibility negative control. Other zero-trade annual runs remain in the
    executed count but not in the active or active-monthly count.
    """
    if not isinstance(registry, dict):
        raise RegistryAuditError("Registry must be a JSON object")
    if registry.get("original_private_zip_sha256") != ORIGINAL_SHA256:
        raise RegistryAuditError("Original-source SHA256 contract changed")
    if registry.get("fixed_roundtrip_all_in_fee_usd_per_oz") != 0.4:
        raise RegistryAuditError("ALL-IN roundtrip fee must remain exactly 0.40/oz")
    if registry.get("research_status") != "HISTORICALLY_EXPOSED_DESIGN_ONLY_NOT_OOS":
        raise RegistryAuditError("Exposed research must not be relabeled OOS")
    batches = registry.get("completed_batches")
    controls = registry.get("feasibility_negative_controls")
    totals = registry.get("totals")
    if not isinstance(batches, list) or not isinstance(controls, list) or not isinstance(totals, dict):
        raise RegistryAuditError("Missing completed batches, controls, or totals")
    seen_ids, seen_files = set(), set()
    specs = active = executed = zero_specs = full_months = active_families = 0
    for batch in batches:
        if not isinstance(batch, dict):
            raise RegistryAuditError("Batch must be an object")
        ident, filename = batch.get("id"), batch.get("file")
        if not isinstance(ident, str) or not ident or ident in seen_ids:
            raise RegistryAuditError(f"Missing or duplicate batch id: {ident}")
        if not isinstance(filename, str) or not filename or filename in seen_files:
            raise RegistryAuditError(f"Missing or duplicate runner: {filename}")
        seen_ids.add(ident)
        seen_files.add(filename)
        if batch.get("years") != [2012, 2013]:
            raise RegistryAuditError(f"{ident}: unexpected design years")
        n_specs = _integer(batch.get("unique_parameter_specs"), f"{ident} specs")
        n_executed = _integer(batch.get(
            "completed_annual_parameter_executions",
            batch.get("completed_annual_replays")), f"{ident} executions")
        n_active = _integer(batch.get(
            "active_annual_replays",
            batch.get("annual_replays_with_filled_trades",
                      0 if ident == "NRF-FAC-005" else batch.get("completed_annual_replays"))),
            f"{ident} active")
        if n_executed != n_specs * 2:
            raise RegistryAuditError(f"{ident}: annual executions do not match 2 design years")
        if n_active > n_executed:
            raise RegistryAuditError(f"{ident}: active exceeds executed")
        if "zero_trade_annual_executions" in batch:
            _assert_equal(n_executed - n_active,
                          _integer(batch["zero_trade_annual_executions"], f"{ident} zero"),
                          f"{ident} zero-trade reconciliation")
        for key in ("completed_monthly_pnl_values", "completed_monthly_values_including_zero_trade",
                    "completed_exit_booked_monthly_values"):
            if key in batch:
                _assert_equal(n_executed * 12, _integer(batch[key], f"{ident} {key}"),
                              f"{ident} all monthly values")
        if "active_monthly_values" in batch:
            _assert_equal(n_active * 12, _integer(batch["active_monthly_values"], f"{ident} active months"),
                          f"{ident} active monthly values")
        if "configs_24_of_24" in batch:
            full_months += _integer(batch["configs_24_of_24"], f"{ident} 24/24")
        if n_active:
            specs += n_specs
            active_families += 1
        elif n_active == 0:
            zero_specs += n_specs
        zero_specs += _integer(batch.get("zero_trade_specs_both_years", 0),
                               f"{ident} both-year zero specs")
        active += n_active
        executed += n_executed

    for control in controls:
        if not isinstance(control, dict):
            raise RegistryAuditError("Negative control must be an object")
        ident = control.get("id")
        if not isinstance(ident, str) or not ident or ident in seen_ids:
            raise RegistryAuditError(f"Missing or duplicate negative-control id: {ident}")
        seen_ids.add(ident)
        n = _integer(control.get("actual_parameter_year_executions"), f"{ident} executions")
        z = _integer(control.get("zero_trade_executions"), f"{ident} zero")
        a = _integer(control.get("active_annual_replays"), f"{ident} active")
        if n != z + a or a:
            raise RegistryAuditError(f"{ident}: negative control not entirely zero-trade")
        executed += n
        zero_specs += n  # Each one-year feasibility trial is a distinct zero-trade spec.

    result = {
        "distinct_parameter_specs": specs,
        "yearly_backtests": active,
        "exit_booked_monthly_points": active * 12,
        "independent_hypothesis_families": active_families,
        "strictly_positive_every_month_in_both_years": full_months,
        "zero_trade_parameter_specs_excluded": zero_specs,
        "zero_trade_yearly_parameter_executions_excluded": executed - active,
        "total_yearly_parameter_executions_including_zero_trade_negative_control": executed,
    }
    for key, value in result.items():
        _assert_equal(value, _integer(totals.get(key), f"totals.{key}"), key)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    args = parser.parse_args()
    data = json.loads(args.registry.read_text(encoding="utf-8"))
    print(json.dumps({"status": "REGISTRY_ARITHMETIC_ONLY_NOT_REPLAY_CERTIFICATION",
                      **audit_registry(data)}, indent=2))


if __name__ == "__main__":
    main()
