# No Risk FX — family-wise monthly block-bootstrap diagnostic (2026-10-30)

**Status: synthetic-only validation; no new Gold ZIP replay or trading claim.**

## Why

Ranking the best of thousands of historical strategies inflates the apparent strength of the winner. A candidate screen that shows 60% positive months does not itself account for the number of attempted variants, dependence between variants, or market regime changes. This optional diagnostic tests a **single predeclared frozen family**, not a handpicked winner.

## Method and contract

`python scripts/research_familywise_block_audit.py --plan /secure/frozen_plan.json --batch-output /secure/frozen_batch --train-start 2012-01 --train-end 2016-12 --block-length 3 --replicates 1999 --seed 20261030`

The script requires the original private dataset SHA256, the frozen engine checkout, a complete batch manifest, and a successful independent `audit_run` reconciliation of **every** defined candidate. Any missing/failed candidate, missing training calendar month, mismatched manifest, or altered source archive fails closed. All selected months are contiguous UTC calendar months. The output `familywise_block_audit.json` is written atomically into the private batch output; the public repository contains no original quotes.

For a training matrix `X` of `T >= 12` months by `K` candidates, let `m_k` be the candidate's observed average monthly net USD/oz, and `M = max_k(m_k)`. Each bootstrap replicate samples circular blocks of length `L` months with replacement until `T` months are selected. **The same sampled calendar indices are applied to all `K` candidates**, preserving contemporaneous cross-candidate dependence. Bootstrap maxima are calculated from mean-centered observations `X[:,k] - m_k`. The reported exploratory upper-tail fraction is `(1 + count(M_null >= M)) / (B + 1)`. Report the 95th percentile of centered null maxima and the winning candidate's training net/positive months. Candidate IDs are sorted for deterministic tie resolution. No review-period values are read.

This is a **dependence sensitivity diagnostic**, not a validated significance test. Centered circular-block resampling assumes enough approximately stationary monthly structure; gold market regimes and overlapping strategy research may violate this. Choosing block length or the candidate universe after looking at results invalidates any nominal inference. The procedure does not adjust for strategy families previously tried and omitted, unpublished failed experiments, fees different from the frozen engine, or future market drift. A low tail fraction does **not** prove an edge, OOS performance, or broker fill feasibility. In particular, it must never be labeled a real-world false-discovery probability or live authorization.

## Verification scope

24 scoped synthetic tests passed locally for the standalone module using **local dependency stubs** for the existing batch orchestrator; these are **not** a full repository or actual-data test. Tests cover deterministic seed, finite/shape/ID validation, 999-replicate lower bound, paired-index behavior versus a slow reference, missing candidates, and complete synthetic manifest wiring. Exact GitHub HEAD CI and actual private-archive integration must be verified separately. No original market ZIP was available in this execution environment.

**New real-data strategy backtests: 0. New verified positive months: 0. Independent untouched OOS: not established. Approved strategies: 0.** Keep PR #1 draft, do not publish private source archives, and do not use these diagnostics for live trading.
