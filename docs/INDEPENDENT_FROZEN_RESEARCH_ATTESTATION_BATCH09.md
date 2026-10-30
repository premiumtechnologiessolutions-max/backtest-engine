# Batch 09 — Independent frozen historical ledger attestation

Date: 2026-10-30. **Research-only; Draft PR.** Exact parent: B08 integrated branch PR #14.

## Engineering gap closed

The B06 worker used to rely on a successful `run_plan` result and hash
of `batch_manifest.json` before marking the task as completed. An altered
or incomplete report after the runner returned could escape that limited
worker-level check. B09 introduces an **independent, second read of all
original on-disk outputs** before committing an artifact digest to the
durable research queue.

`norisk_quant.frozen_batch_attestation.verify_frozen_batch_evidence`:

- Validates the frozen one-job canonical plan using the existing
  `research_batch_orchestrator.expand`, exact canonical 64-hex experiment
  identity and source manifest ID.
- Allows only the currently implemented Gold `m1-sweep`, M1, reference,
  historical-exposed strategy scenario. No native Nova `aql_*` execution.
- Re-reads `batch_manifest.json`, checks exact schema, strategy job ID,
  plan SHA, raw Gold ZIP SHA, pinned 40-character Git SHA and one result.
- Requires the original summary/trades/monthly/weekly evidence files to
  exist as regular owner-only non-symlink, single-hardlink files, with
  bounded file sizes.
- Calls the existing, separately implemented
  `research_batch_orchestrator.audit_run` again against the actual files.
  That function reconciles recorded source+M1 fingerprints, execution
  assumptions, settings, fixed 0.40 USD per-ounce all-in roundtrip cost,
  individual trade records, weekly and monthly aggregates and summary.
- Rejects a modified/failed manifest, changed individual CSV or JSON,
  mismatched source/engine ID, multiple results, symlinks, hardlinks or
  world-readable files. Rechecks SHA for all report files at the end to
  catch tampering during audit.
- Returns a private `HistoricalAttestation` with immutable evidence
  digest. Its public status *never* exposes raw prices, P/L, source file
  SHA, strategy parameters, account scope or ability to trade.
- B06 now requires this separate successful attestation before its
  SQLite queue can store the `historical_audit_pending` artifact hash.
  Failed re-audits are marked rejected for manual investigation, not
  automatically retried or declared profitable.

## Operator-only independent recheck of existing files

On private owner-controlled checkout, after the B06 canonical run
has already produced a frozen plan, original B07 source manifest,
and a complete batch report directory:

    python scripts/verify_frozen_worker_evidence.py --plan PRIVATE_FROZEN_PLAN.json --source-manifest PRIVATE_SOURCE_RECORD.json --output PRIVATE_BATCH_OUTPUT --experiment-id EXACT_CANONICAL_EXPERIMENT_SHA256

The command is read-only, performs no new simulation and prints only
non-sensitive research status. It is not an authenticated Terminal web
service. PRIVATE report files must not be uploaded to public GitHub.

## Validated in CI

- Full independent report audit of a REAL canonical CLI invocation on
  explicitly **synthetic** M1 Bid/Ask quotes (no user market data).
- Deliberate manipulation of trades.csv, weekly.csv, monthly.csv,
  summary.json, batch_manifest.json, missing files, duplicate result
  jobs, source SHA, experiment ID, hardlinks/symlinks and permissions.
- Linux/Windows contract tests (actual POSIX report validation on Linux),
  and full canonical Python regressions.

## Scientific/release blockers

1. No actual original owner-owned Gold market source run at this exact
   source code SHA yet. The local earlier EMA 2024 experiment on an older
   operational checkpoint MUST NOT be represented as this worker's result.
2. Trade fill model remains synthetic reference Bid/OHLC, not broker
   order-book or observed tick execution. Ledger consistency does not
   imply real executability.
3. No independently locked post-selection prospective OOS results,
   no certified every-month positive edge, no real-money trading
   authorization. The fixed 0.40 USD/oz is a user-requested research
   fee scenario, not independently verified broker execution cost.
4. Original Gold ZIP and private customer information stay off public
   repository. POSIX-only actual worker execution; Windows/NTFS ACL
   parity not yet reviewed.
5. B08/B09 still Draft and not deployed to Oracle/Terminal. Authenticated
   private status readouts, backups and full live operational release
   gates remain separate.

See platform issue #6 and prior Draft PR #14.
