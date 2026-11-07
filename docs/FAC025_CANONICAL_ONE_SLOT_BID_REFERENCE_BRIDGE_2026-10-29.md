# FAC025 — canonical one-slot BID-reference replay bridge (2026-10-29)

This change implements a deterministic canonical/fast research replay bridge for the already frozen FAC025-ENTRY-A intents. Code: scripts/research_fac025_canonical_replay.py; synthetic tests: tests/test_research_fac025_canonical_replay.py.

The adapter verifies the frozen policy SHA256, the 72 correlated filter fingerprints, the 60-second deadline, one-slot capacity, the 1.50 target multiple and exactly $0.40/oz ALL-IN fee. It maps frozen intents to canonical market signals, enforces strictly-after decision availability with a 1-nanosecond boundary, and runs one shared portfolio via the canonical and fast engines. It checks all canonical trade columns, every observed M1 equity mark, trade non-overlap and fees. It computes exit-booked UTC monthly net, worst month, positive months and observed M1-close equity drawdown. Correlated settings are NOT independent hypotheses; standalone P/L is never added.

LIMITATION: This is a BID-only synthetic reference replay, not a paired BID/ASK executable-price engine. Input intents and source provenance are not independently authenticated. No original Gold ZIP was available in this run; 0 original-data backtests, new historical monthly P/L N/A, new historical floating DD N/A, 0 approved strategies. No untouched OOS, broker/tick fill or live-trading claim. The next gate is a SHA256-pinned original-source causal replay with paired BID/ASK execution and independent prospective validation. Historical 2012-2016 remain exposed.

Run synthetic regression: python -m pytest -q tests/test_research_fac025_canonical_replay.py. Do not publish raw quotes, credentials or private Gold ZIP. Keep PR #1 Draft/unmerged.
