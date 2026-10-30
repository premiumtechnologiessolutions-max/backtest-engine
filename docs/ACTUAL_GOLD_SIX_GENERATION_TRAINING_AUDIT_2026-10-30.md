# No Risk FX — Six-generation actual Gold ZIP training acceptance (2026-10-30)

## Run scope and evidence

The **original 155,808,257-byte** private `Gold data.zip` was verified by SHA256:

`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`

Completed **six sequential arithmetic proposal generations**, with one new
formula per generation, evaluated separately on exposed full **2012 and 2013**
M1 Gold training years. Each formula/year was executed with **Reference and
Fast** on the original ZIP, then checked against the canonical trade,
monthly, weekly and observed-M1 equity accounting verifiers. The fixed
all-in roundtrip research fee remained **$0.40 per ounce**.

This constitutes **12 formula/year research cases, 24 engine executions,
4,404 total strategy/year trade outcomes** (different hypothetical
strategies; never sum P/L as if they formed one continuous portfolio).
Cumulative fees across these 12 separate scenarios were **$1,761.60**.
The same annual BID/ASK fingerprints were found for each year across all
six generations. Each frozen feedback sidecar hash matched the resulting
next-generation input JSON.

## Annual research outcome (net USD/oz after fixed fee)

| Generation | 2012: trades / net / positive months | 2013: trades / net / positive months | Sum across two separate training-year runs | Positive months |
|---|---|---|---:|---:|
| 1 | 521 / -237.71 / 4 | 617 / +354.54 / 7 | +116.83 | 11/24 |
| 2 | 510 / -362.80 / 2 | 611 / +405.69 / 8 | +42.89 | 10/24 |
| 3 | 489 / -115.46 / 4 | 560 / +253.31 / 7 | +137.85 | 11/24 |
| 4 | 484 / -688.12 / 3 | 543 / +9.03 / 7 | -679.09 | 10/24 |
| 5 | 14 / +96.21 / 4 | 20 / +295.80 / 6 | +392.01 | 10/24 |
| 6 | 13 / +134.90 / 5 | 22 / -199.09 / 4 | -64.19 | 9/24 |

Total: **61 profitable strategy-months out of 144 exposed training
strategy-months**. Generation 5 had both annual totals positive but only
34 completed trades and 10/24 positive months, therefore it does
**not** pass the preregistered training heuristic and cannot be
called an edge.

## Frozen feedback SHA256 receipts

| Generation | SHA256 of verified next training input |
|---|---|
| 1 | `3f9ffbd742e07b12b922e23ce3614de7b9e4ba14308c5ab22b303ffe23177179` |
| 2 | `6900758c720521077cd3f98f06e7712dcaf79b323924eb33e88bdd570af7e24c` |
| 3 | `f4c197b3405ae16ba742d163721feda0844a0dd94926fe8cec94056a4644e4fc` |
| 4 | `46bea9ea0c315a9334a1614d2579f254da30265f2f3f3bc01075d06f2dda0dc3` |
| 5 | `6e8704f73ea22c32dccfa5725d636d621d25db1aff88b0b4fe65aed934290041` |
| 6 | `13870b4f125e01b8b7297590db35d8850381d1b1c233291b58676e47f345b592` |

## Exact scope / restrictions

The historical runs used the archived source checkout from a successful
GitHub Actions verified-code artifact, not the newest post-enhancement
branch checkout. Checked Git blob identities for
`scripts/run_arithmetic_evolution.py`,
`scripts/run_arithmetic_dispatch_training.py`,
`src/norisk_quant/research_evolution.py`,
`src/norisk_quant/math_discovery.py` and
`src/norisk_quant/cli.py` matched the branch at verification.
The archived orchestrator and feedback implementation differ from the
latest branch because newer versions add campaign integrity and
training-memory compaction (the six-generation candidate pool remained
well below 128, so compaction did not apply). **Do not describe this as
a fresh exact-HEAD whole-repository real-data replay.**

Historical 2012–13 have been inspected before and are emphatically
**NOT independent OOS**. No broker ticks, latency/slippage calibration,
margin-risk model, market edge or stable profitable-month guarantee
has been validated. No source ZIP, M1 prices, equity data or individual
trade ledgers were published to GitHub. Do not promote to live trading.
PR #1 remains Draft and must not be merged on this evidence alone.

The next production acceptance gates remain: benchmark hundreds and
then thousands of historical candidate executions on a truly persistent
worker, observe CPU/RAM/disk throughput, verify durable recovery and
live local monitoring, extend beyond the training-only heuristic to
audited failure-conditioned experiments, and collect genuinely
preregistered prospective observations before any OOS claims.
