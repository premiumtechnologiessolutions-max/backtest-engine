"""Synthetic-only calendar/causality tests: no market data or execution."""
from datetime import datetime, timezone, timedelta
import pytest
from scripts import research_job_month_plan as plan


def request(start="2026-11-01", end="2027-10-31"):
    return {"fingerprint": "a" * 64, "evaluation_start": start, "evaluation_end": end}


def test_future_prospective_window_has_no_observed_months():
    slots = plan.plan_month_slots(request(), datetime(2026, 10, 28, tzinfo=timezone.utc))
    assert len(slots) == 12
    assert slots[0]["month"] == "2026-11"
    assert slots[-1]["month"] == "2027-10"
    assert all(s["calendar_status"] == "FUTURE_OR_PARTIAL" for s in slots)
    assert all(s["execution_status"] == "NOT_EXECUTED" and not s["source_verified"] for s in slots)
    assert all(s["monthly_net_pnl_usd_per_oz"] is None for s in slots)
    assert all(s["observed_m1_floating_dd_usd_per_oz"] is None for s in slots)


def test_exact_utc_month_boundary_and_deterministic_slot_id():
    job = request("2026-11-01", "2026-12-31")
    before = plan.plan_month_slots(job, datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc))
    after = plan.plan_month_slots(job, datetime(2027, 1, 1, tzinfo=timezone.utc))
    assert [s["calendar_status"] for s in before] == ["CLOSED_SOURCE_UNVERIFIED", "FUTURE_OR_PARTIAL"]
    assert [s["calendar_status"] for s in after] == ["CLOSED_SOURCE_UNVERIFIED"] * 2
    assert [s["slot_fingerprint"] for s in before] == [s["slot_fingerprint"] for s in after]
    assert all(s["monthly_net_pnl_usd_per_oz"] is None for s in after)


def test_leap_year_and_utc_calendar_month_boundaries():
    slots = plan.plan_month_slots(request("2024-02-01", "2024-03-31"), datetime(2024, 4, 1, tzinfo=timezone.utc))
    assert slots[0]["month_end_exclusive_utc"] == "2024-03-01"
    assert slots[1]["month_end_exclusive_utc"] == "2024-04-01"
    assert len({s["slot_fingerprint"] for s in slots}) == 2


@pytest.mark.parametrize("start,end", [
    ("2026-11-02", "2026-11-30"),
    ("2026-11-01", "2026-11-29"),
    ("2026-12-01", "2026-11-30"),
])
def test_partial_or_reversed_periods_fail_closed(start, end):
    with pytest.raises(ValueError):
        plan.plan_month_slots(request(start, end), datetime(2027, 1, 1, tzinfo=timezone.utc))


@pytest.mark.parametrize("as_of", [
    datetime(2026, 10, 28),
    datetime(2026, 10, 28, tzinfo=timezone(timedelta(hours=2))),
    None,
])
def test_non_utc_or_missing_clock_rejected(as_of):
    with pytest.raises(ValueError, match="UTC"):
        plan.plan_month_slots(request(), as_of)


def test_cap_rejects_unbounded_plans():
    with pytest.raises(ValueError, match="120-month"):
        plan.plan_month_slots(request("2020-01-01", "2031-01-31"), datetime(2026, 10, 28, tzinfo=timezone.utc))


def test_plan_job_calls_preflight_and_does_not_mutate_queue(tmp_path, monkeypatch):
    job = request("2026-11-01", "2026-11-30")
    called = []
    def preflight(root, fingerprint):
        called.append((root, fingerprint))
        return {"fingerprint": fingerprint, "status": "MATCHED_METADATA_ONLY_NOT_EXECUTED"}
    monkeypatch.setattr(plan, "preflight_job", preflight)
    monkeypatch.setattr(plan, "list_jobs", lambda root: [job])
    result = plan.plan_job(tmp_path, job["fingerprint"], datetime(2026, 10, 28, tzinfo=timezone.utc))
    assert called == [(tmp_path, job["fingerprint"])]
    assert result["planning_only"] is True
    assert result["calendar_closed_months"] == 0
    assert result["source_verified_months"] == 0
    assert result["backtests_executed"] == 0
    assert result["monthly_pnl_observations"] == 0
    assert result["slots"][0]["execution_status"] == "NOT_EXECUTED"


def test_plan_job_rejects_preflight_failure(tmp_path, monkeypatch):
    def deny(*args):
        raise ValueError("wrong checkout")
    monkeypatch.setattr(plan, "preflight_job", deny)
    with pytest.raises(ValueError, match="wrong checkout"):
        plan.plan_job(tmp_path, "a" * 64)


def test_slot_fingerprint_is_bound_to_frozen_request():
    as_of = datetime(2027, 1, 1, tzinfo=timezone.utc)
    a = plan.plan_month_slots(request("2026-11-01", "2026-11-30"), as_of)[0]
    job = request("2026-11-01", "2026-11-30")
    job["fingerprint"] = "b" * 64
    b = plan.plan_month_slots(job, as_of)[0]
    assert a["slot_fingerprint"] != b["slot_fingerprint"]
