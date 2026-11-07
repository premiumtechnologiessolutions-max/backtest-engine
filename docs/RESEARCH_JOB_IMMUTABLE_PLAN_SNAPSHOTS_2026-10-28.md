# Immutable monthly plan snapshots — 2026-10-28

`scripts/research_job_plan_snapshot.py` persists **planning metadata only** for
already queued frozen requests. It re-runs the existing clean-checkout preflight
and deterministic UTC monthly planner before creating or verifying any record.

From a trusted local repository checkout:

```bash
python scripts/research_job_plan_snapshot.py persist --fingerprint <queued-request-sha256>
python scripts/research_job_plan_snapshot.py verify --fingerprint <queued-request-sha256>
python -m pytest -q tests/test_research_job_plan_snapshot.py
```

Snapshots are stored under ignored local `reports/research_jobs/monthly_plans/`,
never in public GitHub. The 0700 directory and 0600 O_EXCL files reject
symlinks, hardlinks, unexpected permissions, oversized files and mismatched
content. Persist is idempotent, not an overwrite; verify recomputes all month
slots from current frozen inputs and rejects drift. The SHA256 digest detects
accidental changes but is **not an authentication signature** against the
same-OS-user adversary. Exact clean checkout preflight remains mandatory.

This is an immutable **plan snapshot**, NOT an execution checkpoint. Every slot
is `PLANNED_ONLY_NOT_EXECUTED`; backtests executed = 0; source-verified
months = 0; P/L and floating DD = N/A. It does not read Gold ZIP, create
fabricated market minutes, launch workers, resume a partial backtest, or certify
OOS. Future resumable execution needs separate authorized sandboxed workers,
atomic evidence ledgers, source coverage and canonical parity, shared capacity,
cost/embargo controls, and a complete prospective period. PR #1 remains Draft.
