# V5.1 Quant Research Brain — training-integrity session (2026-10-29)

## Canonical GitHub branch change

- Added `src/norisk_quant/research_training_integrity.py`: a standalone training-only, fail-closed scoring-evidence preflight. It checks complete and unique chronological year membership; all 12 calendar months per year; finite numeric monthly returns and per-year totals; canonical $0.40/oz roundtrip fee; fee = count × $0.40; recorded positive-month counts; nonboolean nonnegative trade/gap/end-of-data counts; successful accounting audit; and cross-year numeric overflow. Extra review-year observations are rejected rather than influencing selection.
- Added `tests/test_research_training_integrity.py` with adversarial mismatched-month, tampered-P/L, cost, count, year injection and overflow cases.
- This strict module is a **standalone boundary for future controller integration**. It does NOT mean the V5 adaptive controller and independent auditor are fully migrated into this GitHub repository. Keep PR #1 Draft and unmerged.

## Separate local V5.1 release QA (not HEAD certification)

A revised standalone V5.1 archive was assembled locally with enhanced `scripts/research_brain.py` annual evidence checks, stricter source-verification status, review-score separation, regression tests, and SHA256 release inventory. The archive was extracted to a fresh folder and its 23-file manifest verified.

Selected local tests: **73 passed** (math grammar, Brain training, tamper/error guards, independent reference-audit logic, V5 launcher logic). This test harness used an **older October 26 engine snapshot**, not the exact current GitHub head; neither the full current-repository suite nor Windows runtime is certified by these passes.

Private original Gold source ZIP had source SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. No raw market data, private trade/equity ledger, or the full archive was pushed to GitHub.

## Real historical exploratory QA (local older engine; 2012–2013)

Two arithmetic rule candidates were run, both rejected:

| Training formula | Trades | Positive months | Net USD/oz | Outcome |
| --- | ---: | ---: | ---: | --- |
| `f64aacffca8029d48...` | 3,280 | 8/24 | -893.46 | rejected |
| `1190545949b2e8b5...` | 3,273 | 4/24 | -1,551.64 | rejected |

The first formula received full *local* reference-vs-fast audit: 1,611 trades in 2012, 1,669 in 2013, matching all 15 ledger fields and observed M1 equity samples; no numeric deviation. The second was not independently audited. Both are unprofitable in the training interval. The experiment ran on a non-HEAD local research checkout and has no exact-head source-parity claim.

## Open release gates

1. Wire and test the standalone strict preflight inside the version-pinned, migrated Research Brain controller, and freeze parameter/feature universe before review data.
2. Obtain full latest-GitHub-HEAD CI and independent raw-source replay on the exact execution code. Prior successful CI checks don't automatically certify new commits.
3. Confirm clean Windows Python 3.12 startup and overnight crash/resume reference-audit test.
4. Pre-register a genuinely unexamined prospective holdout; all historical years explored in this project are exposed.
5. Validate broker-specific ticks/Bid-Ask/fill assumptions and real transaction costs before any trading claim.

**No strategy earned an independently verified edge or every-month profitability. No live trade authorization. The repository remains PUBLIC, therefore private market data must stay local.**
