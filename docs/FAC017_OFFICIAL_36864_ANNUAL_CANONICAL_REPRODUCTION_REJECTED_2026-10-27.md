# FAC017 — official-source full-grid and canonical verification (2026-10-27)

**Decision: REJECT.** This is verification of the *already preregistered and locally executed* FAC017 family, not a newly invented strategy and not an additional batch of independent tests. All 2012–2013 results are historically exposed design observations, **not clean OOS**.

## Provenance and privacy

- Frozen before outcomes: [FAC017 preregistration](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/e88adcea2f00927e15d93e37d11e8f95e7680911); same 18,432 correlated specs in each of 2012/2013, not 18,432 independent hypotheses.
- Recovered original private `Gold data.zip` locally and verified SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
- Replayed **the actual frozen runner** `scripts/batch_two_bar_shock_reversal_grid.py` from the official exact-head GitHub Actions source artifact **12715291292** at commit `94f9115c9ef367d83989f5cd6ebce3d8c364b821` (runner Git blob `630092717d81c5ccf1d49bb39c4e379ca35a84ca`).
- Original BID/ASK M1, full annual CSVs and detailed trade ledgers stayed local. No raw quotes uploaded to the public repository or CI.

## Verified results

| Metric | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Executed annual parameter replays | 18,432 | 18,432 | **36,864** |
| Replays with fills | 16,896 | 17,728 | **34,624** |
| Zero-trade replays | 1,536 | 704 | **2,240** |
| Monthly P/L values including zero-trade | 221,184 | 221,184 | **442,368** |
| Unique causal entry streams | 254 | 260 | correlated |
| Max positive months in an individual year | 10/12 | 11/12 | **20/24 for one parameter ID** |

- All **36,864** official-runner annual rows and **442,368** monthly values reproduced the earlier local exports exactly (all shared fields, **max numeric delta 0**; annual CSV SHA256 checks in the JSON manifest).
- **5/18,432** parameter IDs reached at least 18/24 positive months; **0** reached 24/24 and **0** passed the preregistered joint screen. **1,080** IDs were annual-net positive in both years but failed the joint constraints.
- The posthoc maximum-positive-months ID `VSE17_N32_Q2.50_R0.55_ACTIVE_ALL_SL2.25_TP0.50` achieved **9/12** positive months and **-$4.74875/oz** in 2012, **11/12** and **+$7.38875/oz** in 2013. Combined **20/24**, **+$2.64000/oz** after **$16.40/oz** fixed total roundtrip fees for 41 trades. Worst month **-$5.76625/oz** and maximum annual M1 floating drawdown **$11.13625/oz**. The frozen gate requires **at least 100 trades in each year**; this candidate has only **22/19** and loses 2012: **REJECT**.
- One-position **per annual replay**; do not sum individual candidate P/L into a fictional shared-capacity portfolio.

## Execution and parity

- Exact fixed **$0.40/oz ALL-IN roundtrip**, signal at completed M15 close, next observed eligible M1 open within 60 seconds, stop-first same-minute ambiguity, adverse gap-through, no fabricated missing minutes. Last-completed H1 regime, causal volatility halt and DST-aware London/New York sessions.
- Official `run_fast` parity from frozen runner: **4 samples/year = 8**; all annual monthly values, fees, trades, M1 floating drawdown match.
- Separate full-year `execution.run` vs `run_fast` verification: **2 distinct parameter IDs × 2 years = 4 scenarios**; **866 trades** checked in all **15 trade ledger fields** and **1,410,584 observed M1 equity marks** (705,292 distinct minute timestamps across the two years, repeated across scenarios). **Exact equality** of trade/equity values, exit-booked monthly P/L, fees, and drawdown; no tolerated discrepancy.
- Local synthetic FAC017 batch and arithmetic-audit tests: **26/26 passed** on Python 3.13.5 (not the pinned CI Python). Exact official source head CI [40462258228](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40462258228) **932/932 pytest passed** on pinned Python 3.12.15, plus compile/dependency/CLI/synthetic smoke. The **results/registry commit created after this report requires its own exact-head CI**; do not misattribute previous green CI to a later commit.

## Decision, limitations, and next steps

**REJECT; do not retune on 2012–2016.** FAC017 can now be promoted from *pending local replay* to *official-source verified historical rejected batch* in the registry. This verification **does not add a second 36,864 executions**: it confirms the same prior runs and only now includes their active counts in the certified factory totals.

No independent prospective/embargoed OOS, broker BID/ASK tick-fill validation, or real trading approval. Keep Draft PR #1 unmerged. For a future portfolio, enforce **one shared capacity and causal pre-known risk halt**; do not add separate strategy P/L series.

Machine-readable audit: [FAC017 official verification manifest](../research/FAC017_OFFICIAL_SOURCE_REPLAY_VERIFICATION_2026-10-27.json).
