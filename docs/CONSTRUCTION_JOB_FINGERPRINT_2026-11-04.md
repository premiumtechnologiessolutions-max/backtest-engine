# Inert construction job fingerprint — 2026-11-04

The pure `scripts/construction_job_fingerprint.py` helper first applies the deny-by-default `construction_job_admission.admit` schema, then hashes four normalized immutable fields (kind, name, source_commit, fixture) with canonical JSON SHA-256. Reordered keys retain the same identity; changes in any admitted field change the identity. Unknown fields and market/backtest/live job types are rejected.

This is an **identity primitive only**, not a durable queue, lock, authorization token, provenance proof, content digest, or execution sandbox. In particular, fixture existence/content and actual source-commit validity are not verified. Future storage must enforce unique IDs, transactional fencing, actor authorization and atomic state transitions separately. No automatic workers, subprocesses, external adapters, market data or actual backtests are involved.

Focused synthetic check: `python -m pytest -q tests/test_construction_job_fingerprint.py`. CI on the resulting branch head must be checked separately. Historical registry unchanged. Draft PR must remain unmerged.
