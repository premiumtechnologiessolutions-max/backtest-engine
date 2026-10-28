"""Deterministic UTC month-slot planner for frozen, preflight-checked jobs.

Planning only: NEVER starts backtests, reads quotes, writes checkpoints,
claims data availability, or marks a month as an observed result.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

try:
    from scripts.research_job_preflight import preflight_job
    from scripts.research_job_queue import ROOT, _period, list_jobs
except ModuleNotFoundError:  # direct invocation from repository root
    from research_job_preflight import preflight_job
    from research_job_queue import ROOT, _period, list_jobs

MAX_MONTHS = 120


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), 1 if day.month == 12 else day.month + 1, 1)


def plan_month_slots(job: dict, as_of_utc: datetime) -> list[dict]:
    """Plan closed UTC calendar months; no claims of verified market coverage.

    Caller must first verify the queue record with list_jobs/preflight_job.
    The UTC calendar is NOT a substitute for M1 source gap/DST auditing.
    """
    if (not isinstance(as_of_utc, datetime) or as_of_utc.tzinfo is None
            or as_of_utc.utcoffset() != timedelta(0)):
        raise ValueError("as_of_utc must be a timezone-aware UTC datetime")
    start = _period(job["evaluation_start"])
    end = _period(job["evaluation_end"])
    if end < start or start.day != 1 or _next_month(date(end.year, end.month, 1)) - timedelta(days=1) != end:
        raise ValueError("Monthly plan requires full UTC calendar-month evaluation bounds")
    cursor = start
    months = []
    stop = end + timedelta(days=1)
    while cursor < stop:
        if len(months) >= MAX_MONTHS:
            raise ValueError("Monthly plan exceeds 120-month resource cap")
        next_start = _next_month(cursor)
        if next_start > stop:
            raise ValueError("Incomplete evaluation month")
        payload = {
            "schema_version": 1,
            "request_fingerprint": job["fingerprint"],
            "month_start_utc": cursor.isoformat(),
            "month_end_exclusive_utc": next_start.isoformat(),
        }
        slot_id = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")).hexdigest()
        calendar_closed = as_of_utc >= datetime(next_start.year, next_start.month, 1, tzinfo=timezone.utc)
        months.append({
            "month": cursor.strftime("%Y-%m"),
            "month_start_utc": cursor.isoformat(),
            "month_end_exclusive_utc": next_start.isoformat(),
            "slot_fingerprint": slot_id,
            "calendar_status": "CLOSED_SOURCE_UNVERIFIED" if calendar_closed else "FUTURE_OR_PARTIAL",
            "source_verified": False,
            "execution_status": "NOT_EXECUTED",
            "monthly_net_pnl_usd_per_oz": None,
            "observed_m1_floating_dd_usd_per_oz": None,
        })
        cursor = next_start
    return months


def plan_job(root: Path, fingerprint: str, as_of_utc: datetime | None = None) -> dict:
    """Require exact clean checkout preflight; emit read-only slots to stdout."""
    verified = preflight_job(root, fingerprint)
    jobs = [job for job in list_jobs(root) if job["fingerprint"] == verified["fingerprint"]]
    if len(jobs) != 1:
        raise ValueError("Verified job changed during monthly planning")
    now = datetime.now(timezone.utc) if as_of_utc is None else as_of_utc
    slots = plan_month_slots(jobs[0], now)
    return {
        "request_fingerprint": verified["fingerprint"],
        "metadata_preflight": verified["status"],
        "planning_only": True,
        "backtests_executed": 0,
        "monthly_pnl_observations": 0,
        "source_verified_months": 0,
        "calendar_closed_months": sum(s["calendar_status"] == "CLOSED_SOURCE_UNVERIFIED" for s in slots),
        "slots": slots,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fingerprint", required=True, help="Existing local frozen request SHA256")
    args = parser.parse_args(argv)
    print(json.dumps(plan_job(ROOT, args.fingerprint), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
