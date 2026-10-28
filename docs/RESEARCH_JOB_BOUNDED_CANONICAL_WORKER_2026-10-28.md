# Frozen Research Job — bounded canonical month worker (2026-10-28)

An explicit offline worker now bridges **verified local queued requests** and the existing **canonical, resumable historical batch runner**. This is an execution-capable implementation, **not evidence of an executed original-data backtest**.

## Operation

1. Queue a frozen FAC request and persist its immutable monthly slot snapshot using the existing local-only intake and snapshot commands. The request pins the clean Git HEAD, original frozen specification and registry hashes.
2. Prepare a **private, owner-only (0600), absolute-path canonical JSON batch plan** for exactly one UTC month. Its source SHA256 must equal the original Gold ZIP SHA256 (1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121), its engine_commit must match the queued clean HEAD, and every expanded canonical job must span exactly the month. Only the existing historical_exposed batch schema is accepted; no forward/OOS certification.
3. Run locally: python -m scripts.research_job_worker bind --fingerprint <64-hex> --month 2012-01 --plan /private/month-plan.json. This atomically stores an owner-only, immutable plan under ignored reports/research_job_execution_plans. It never reads market data.
4. Preview: python -m scripts.research_job_worker run --fingerprint <64-hex> --month 2012-01. This validates the bound plan without execution.
5. Only after the month has closed in UTC and the exact clean pinned checkout is present, explicitly run: python -m scripts.research_job_worker run --fingerprint <64-hex> --month 2012-01 --execute --max-jobs 10.

The worker holds the existing exclusive month lease throughout canonical execution, rechecks frozen inputs under lock, enforces 1..20 jobs per invocation, and stores runs only in an owner-only local directory keyed by request and month. The canonical runner verifies the original private source hash, fixed $0.40/oz all-in roundtrip, strategy specs, exact engine revision and all previously completed manifest evidence; subsequent invocations resume without counting verified completed jobs as new backtests. Incomplete or unverified output fails closed. There is no live trading, no broker connection, no data upload and no cost-bearing cloud job.

## Limits and release gates

The queue's frozen MD/JSON hypothesis and the private executable canonical plan are **separate**: this adapter binds the latter immutably before results, but does not prove that its trading logic was independently preregistered beyond the recorded source, date and commit constraints. A plan created after observing outcomes is not clean OOS. Do not infer independence from parameter-grid size. This worker does not provide cross-plan strategy fingerprint deduplication, global portfolio shared capacity, a race-free adversarial filesystem sandbox, automatic scheduling, memory/resource quotas, a prospective source manifest, or verified monthly M1 floating drawdown. Canonical execution still has its own per-job timeout and local resources are operator-managed. Execution on private original Gold ZIP **has not been performed by this patch**. No registry research totals or monthly returns were changed.

Keep PR #1 Draft/unmerged. Never commit private BID/ASK or the ignored reports tree. Final adoption requires real-source canonical/independent parity, cost and gap audit, portfolio capacity, embargo/multiple-testing controls, prospective OOS and passing exact-head CI.
