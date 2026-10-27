# Quant Research Terminal — offline research-job intake (2026-10-27)

**Scope: safe request registration only. This is NOT a worker, scheduler, backtester, resumed run, trading signal, or verified performance report.**

The new `scripts/research_job_queue.py` records a frozen research request in `reports/research_jobs/<fingerprint>.json`. It never invokes the engine, downloads data, uses a network API, opens MT5, or executes an arbitrary command. No user-supplied shell command or raw BID/ASK quote path is accepted.

## Example (repository root)

```sh
python scripts/research_job_queue.py enqueue \
  --family NRF-FAC-024 \
  --spec docs/FAC024_PROSPECTIVE_SPREAD_RECOVERY_SWEEP_2026-10-27.md \
  --commit <40-character-reviewed-source-commit-SHA> \
  --start 2026-11-01 --end 2027-10-31
python scripts/research_job_queue.py list
python -m pytest -q tests/test_research_job_queue.py
```

The intake fingerprint is SHA256 of canonical JSON containing family ID, SHA256 of the existing frozen spec, SHA256 of the current registry, requested source commit, explicit evaluation dates and the permanent state `QUEUED_NOT_EXECUTED`. The source-commit format is validated but **its existence, integrity, or exact-head CI are not authenticated by this offline intake**. The JSON record is owner-only (0600), stored in an owner-only directory (0700), created atomically with exclusive creation, and repeated identical requests are idempotent. A mismatched existing record or modified fingerprint fails closed on read.

The registry and spec are **not copied** into the queue. The queue does not expose private prices or create any P/L observations. Queue entries must never be counted as completed research or prospective OOS. No strategy has been certified by this feature.

## Outstanding before enabling safe execution

1. A permissioned worker, explicit job allowlist, cancellation, resource budgets, sandboxing, resumable checkpoints, locks, and stale-worker recovery. Until these exist, there is intentionally **no execution or resume operation**.
2. Binding a source-commit fingerprint to the exact reviewed GitHub commit and successful CI, plus verifying the registry and spec match that commit.
3. Original-source manifest and frozen prospective month gate, canonical vs fast parity, shared-capacity portfolio checks, and source-verified monthly P/L and floating M1 drawdown.
4. Security and accessibility review for any future UI that can enqueue jobs; the current terminal remains offline read-only.

The current public GitHub repository must not contain `Gold data.zip`, private BID/ASK M1, credentials, or run artifacts with sensitive data. Keep PR #1 Draft/unmerged; this feature changes no fee assumptions, privacy/billing policy, or live-trading state.
