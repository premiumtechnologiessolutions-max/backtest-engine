# Quant Research Terminal — read-only frozen-job preflight (2026-10-28)

This adds scripts/research_job_preflight.py, a **non-executing** gate for queued research requests. The intake queue remains immutable and its QUEUED_NOT_EXECUTED state is never mutated by this command.

## Usage

Run python scripts/research_job_queue.py list, then python scripts/research_job_preflight.py --fingerprint <64-lowercase-hex-job-fingerprint>. Synthetic tests: python -m pytest -q tests/test_research_job_preflight.py.

The preflight fails closed unless: the queued record is uniquely present and passes existing strict owner-only/file integrity checks; the current frozen-spec and registry file SHA256 hashes equal the hashes captured at enqueue; and the **actual local git rev-parse --verify HEAD** matches the queued source commit. A mismatch requires a **new** frozen request, never rewriting an existing fingerprint or silently reusing a stale job. No user-provided commit override exists on the CLI.

Successful output says MATCHED_METADATA_ONLY_NOT_EXECUTED and explicitly reports **0 new backtests / 0 new monthly P/L**. This is *not* permission to execute, a worker lease, a resume checkpoint, a CI pass, a proof of original market-data provenance, or prospective OOS certification. The preflight now also checks `git status --porcelain --untracked-files=no` and rejects any staged or unstaged **tracked** changes before reporting a matching frozen commit. This does **not** reject untracked files or prove that imported code is free of untracked shadow modules; it is not a security boundary against malicious processes running under the same local user account. Future authorized execution still needs isolated private-data access, explicit operator authorization, resource limits, lease/lock/checkpoint protocol, and independent canonical execution parity.

No trading, broker integration, raw BID/ASK data, privacy/billing changes, or new strategy claims. Keep PR #1 **Draft/unmerged**. Historical 2012–2016 data are exposed design periods; no prospective month is yet complete.
