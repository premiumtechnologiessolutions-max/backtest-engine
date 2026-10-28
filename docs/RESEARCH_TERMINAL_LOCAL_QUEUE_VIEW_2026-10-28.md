# Offline local Research Jobs view — 2026-10-28

This change adds an **explicit opt-in** Research Jobs tab to the existing
Arabic/English, responsive, offline Quant Research Terminal.

Run `python scripts/research_terminal.py --include-local-jobs` locally.
The default terminal does **not** embed any queue records. Opt-in calls
`list_jobs(ROOT)`, which checks record integrity and POSIX owner-only
permissions, and aborts before output if any entry is tampered or unsafe.
The output shows a fingerprint, family, evaluation window, frozen commit
prefix and the literal QUEUED / NOT EXECUTED status. Source-verified
monthly P/L, worst month, floating drawdown, preflight and OOS are **N/A**.

This view does not start a worker, change queue states, resume runs, fetch
data, or submit orders. Static HTML can disclose local job fingerprints
if shared; keep generated reports private. The raw Gold ZIP is never
accessed or uploaded. Existing audited factory totals remain unchanged.

Focused tests:
`python -m pytest -q tests/test_research_terminal.py`

Remaining gates: operator-authorized isolated execution worker, bounded
resources, immutable checkpoints, resume/lease, actual private-source
canonical parity, independent prospective OOS and full CI. PR #1 stays Draft.
