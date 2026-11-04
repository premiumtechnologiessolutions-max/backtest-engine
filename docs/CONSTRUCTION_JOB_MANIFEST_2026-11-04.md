# Inert construction job manifest — 2026-11-04

## Purpose
`scripts/construction_job_manifest.py` converts the in-memory `ConstructionLedger` into deterministic, read-only JSON-compatible metadata. Its SHA-256 covers sorted canonical records. The manifest always reports `completed_jobs=0`, `monthly_pnl=null`, `floating_drawdown=null`, `execution_started=false`, and `market_data_accessed=false`. These values describe this **inert ledger only**, not the overall repository or prior historical research.

## Safety and validation
Only a `ConstructionLedger` instance is accepted. All snapshot entries must have lowercase 64-hex fingerprints, lowercase 40-hex source commits, the inert state `RECORDED_NOT_EXECUTED`, and unique fingerprints. Malformed or falsely executed records are rejected, not silently displayed. There are no market-data reads, workers, schedulers, network calls, or file writes in this module.

## Synthetic verification
`tests/test_construction_job_manifest.py` defines six synthetic-only unit tests: empty/inert metadata, deduplication and stable hashing, commit-sensitive hash, type rejection, malformed record rejection, and false executed-state rejection. CI results must be checked for the final commit before calling this batch CI-verified.

## Remaining engineering
This is **not** a persistent job queue, authorization boundary, tamper-proof audit log, proof of completed execution, or market-results verifier. Still required: durable transactional storage, atomic leases, RBAC, signed/verified provenance, resumability, resource quotas, accessible bilingual UI, synthetic integration/security testing, and explicit construction readiness review. No real-data benchmark/replay/parity or live trading is authorized. PR #1 remains Draft.
