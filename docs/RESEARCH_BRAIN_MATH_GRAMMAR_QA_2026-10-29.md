# Research Brain arithmetic grammar — local training QA, 2026-10-29

**Status: experimental research only; NOT a verified market edge.**

## Code added to this branch

- `src/norisk_quant/math_discovery.py` — causal M1 arithmetic grammar (six bounded price features, five binary operators, immutable formula IDs, fixed SL/RR and cooldown).
- `tests/test_math_discovery.py` — **20 scoped local tests passed** against the matching module bytes: no lookahead on future append, missing-minute invalidation, strict parameter validation, deterministic formula identity, and independent reference/fast synthetic trade replay at **$0.40/oz**.
- Module Git blob `06d63cdd22505d4195cd69e800a56d50881441a6`; test blob `61b3bc9d7218d2af624ecfa6ccb8f07c46fbfc00`.

## Separate private-source training QA

A local, **not yet GitHub-committed** V4 adaptive controller and reference auditor were run on the original Gold archive. Source SHA-256 was checked externally as `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Training covered **2012 and 2013 only**, with **10 completed formula candidates / 20 annual executions**. All ten failed the exploratory training screen: eight had negative net and two had no trades.

The leading formula produced **-$893.46 USD/oz** net, **8/24 positive months**, **3,280 trades** across the two independently simulated annual periods, and **$1,312.00** total fees. An independent reference executor matched the fast executor on **all 15 trade fields for 1,611 trades in 2012 and 1,669 trades in 2013**, maximum numeric difference 0, with marked equity also reconciled. Checkpointing resumed interrupted training and reference audit work without repeating completed years.

The controller was run in **unpinned local QA mode**, so this is **not** a current-GitHub-HEAD controller certification. Raw quotes, trade ledgers and private archive are **not** committed. The private local proof bundle contains formulas, monthly aggregates, source fingerprints, and audit receipts.

## Remaining release gates

1. Integrate and test the adaptive controller, reference auditor, and Quant Lab UI into the canonical repository, with source-commit pinning and an immutable campaign.
2. Run full repository pytest/CI at the exact resulting HEAD; do not inherit earlier CI passes.
3. Complete official 13-field original-source replay at the exact execution-code revision. A fresh long local rerun attempted in this session **timed out** and is not reported as passed; earlier successful frozen-replay evidence belongs to an older pinned execution snapshot.
4. Freeze any candidate before genuinely prospective data; previously explored historical years do not qualify as untouched OOS.
5. Obtain independent broker tick/fill validation before any live-trading claim.

No monthly-profit guarantee, trading approval, or broker order integration. Keep PR #1 Draft. GitHub reports this repository **PUBLIC**, despite the requested private designation; no private raw market data is uploaded.
