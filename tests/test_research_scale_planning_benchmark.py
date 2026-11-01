"""Specification capacity only, not proof of real market replay throughput."""
import pytest

from scripts.research_scale_planning_benchmark import benchmark, frozen_plan


def test_twenty_thousand_distinct_jobs_plan_without_market_access():
    receipt = benchmark(20000)
    assert receipt["jobs_defined"] == 20000
    assert receipt["unique_job_ids"] == 20000
    assert receipt["unique_strategy_specs"] == 20000
    assert receipt["invocations_needed_if_all_executed"] == 40
    assert receipt["market_backtests_executed"] == 0
    assert receipt["independent_oos_proven"] is False
    assert receipt["status"] == "SPECIFICATIONS_EXPANDED_NO_MARKET_EXECUTION"
    assert receipt["plan_sha256"] == benchmark(20000)["plan_sha256"]


def test_small_budget_receipt_is_only_a_dry_run():
    receipt = benchmark(100, max_jobs_per_invocation=10)
    assert receipt["invocations_needed_if_all_executed"] == 10
    assert receipt["market_backtests_executed"] == 0


@pytest.mark.parametrize("count", [0, 1, 99, 101, 50001, -100, True, 100.0])
def test_invalid_scale_request_fails_closed(count):
    with pytest.raises(ValueError, match="multiple of 100"):
        frozen_plan(count)


@pytest.mark.parametrize("budget", [0, 501, True, 1.0])
def test_invalid_per_invocation_budget_fails_closed(budget):
    with pytest.raises(ValueError, match="job budget"):
        benchmark(100, max_jobs_per_invocation=budget)
