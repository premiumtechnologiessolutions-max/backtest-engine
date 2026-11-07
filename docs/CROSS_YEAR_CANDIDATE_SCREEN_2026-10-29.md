# Cross-Year Candidate Screening — 2026-10-29

## Why this component exists

The No Risk FX frozen batch runner produces one audited result per annual job. The new factory defines 228 unique parameter identities repeated across completed years. Ranking each year in isolation would confuse separate annual *measurements* with different strategies and prevent meaningful multi-year consistency research.

The new scripts/research_cross_year_candidate_screen.py groups annual jobs by an immutable SHA-256 identity over strategy, timeframe, execution engine and all parameter values, excluding only the annual start/end boundaries. Every candidate must have exactly one full-year result per requested year; duplicate year/spec pairs are rejected.

## Evidence and eligibility

- Recheck frozen plan/schema/source/engine SHA and every existing recorded annual run using the canonical batch.audit_run implementation (monthly, weekly, trade ledger reconciliation; canonical fixed $0.40/oz).
- Require all 12 monthly P/L and trade count cells for every annual result; refuse tampered or misreported data.
- Compare the same candidate across selected training years and subsequent later-review years. Training only controls eligibility and rank. Later-review results can be displayed but never enter sorting or eligibility.
- Training heuristic: >=20 trades, >=60% positive training months, positive training net USD/oz, and ZERO flagged uncertain-gap trades and ZERO synthetic end-of-data forced closures in training. These are exploratory rules, not a statistical significance proof, no guarantee of positive future months.
- Explicit fail-closed incomplete-universe policy: if ANY candidate is missing required annual runs, all training ranks are set to null and any previously eligible label becomes NOT_ELIGIBLE_BATCH_INCOMPLETE. The program still reports audited descriptive metrics and missing years; it NEVER promotes a partially executed search batch.
- All output is tagged HISTORICAL EXPOSED, independent_oos_proven=false, and no multiple-comparison correction. The displayed drawdown is based on month-end closed P/L only, not intramonth floating risk.
- HTML & JSON exports are local and private; the batch output lock prevents conflicting readers/writers.

## Usage (only when an original private, SHA-pinned frozen batch exists)

python -m scripts.research_cross_year_candidate_screen --plan /private/plan.json --batch-output /private/batch --train-years 2012,2013,2014,2015,2016 --review-years 2017,2018,2019,2020

These historical years have already been researched or exposed; the label is NEVER fresh independent OOS. Generating the report does not execute outstanding backtests.

## Verification

- 10/10 isolated synthetic cross-year screening tests locally passed: grouping identity across annual windows, training-only ranking under arbitrarily changed later outcomes, missing-year incomplete status, zero training eligibility after gap/forced-close exposures, independent ledger tamper rejection, duplicate annual spec rejection, reversed/overlapping year bounds, entirely unexecuted manifest.
- 67/67 local tests across the new M1/TF Sweep models, reference/fast CLI reporting, 3192-spec grid factory and cross-year screen passed on extracted older core + locally reconstructed components. This is NOT the entire latest GitHub repository test suite.
- Additional full-HEAD GitHub test tests/test_cross_year_grid_design.py is committed to check that actual batch.expand produces 456 annual jobs but exactly 228 stable strategy identities across two years; full CI execution NOT verified on this latest HEAD.
- Pinned Python3.12 pytest/CI and original SHA-pinned Gold ZIP 13-field replay remain release blockers. Prior 2012/2017/2020/2024 BOS/H1 results were negative, not fixed by this selection implementation.

No raw market data was uploaded; PR #1 must stay Draft/unmerged. No live or monthly-profit assertions.
