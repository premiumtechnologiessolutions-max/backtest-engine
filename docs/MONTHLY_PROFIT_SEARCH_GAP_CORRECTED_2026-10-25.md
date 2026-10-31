# Monthly-profit research checkpoint — 2026-10-25

**Status:** research diagnostic, NOT an all-month profitable strategy and NOT certified central-engine parity.

Source XAUUSD Gold data.zip original 17 annual M1 Bid/Ask JSON files (2010-Sep20 2026); SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`, raw ZIP stays outside GitHub. Fixed research cost **$0.40/oz ALL-IN per completed roundtrip**; synthetic mid +/-0.20 entry/exit, no additional commission/variable spread/slippage. M1 OHLC not tick replay; SL assumed before TP if both touch an M1 candle.

## Actual work, newly run Oct 25 2026

- Repaired and reran M01 RSI **108 configurations** and M02 Stochastic **12 configurations**, removing incorrect mandatory exit when first >10min quote gap is encountered. Positions now carry outstanding SL/TP into first resumed quote (but exact intragap fills cannot be reconstructed). Reproducing scripts: `nrf_m01_rsi_gap_carry_20261025.py`, `nrf_m02_stochastic_gap_carry_20261025.py` within conversation checkpoint `NoRiskFX_Monthly_Profit_Research_Checkpoint_2026-10-25.zip`; not currently uploaded as repository executable code.
- RSI audit: **163,383 simulated trades across 108 overlapping configurations**, only **one design-eligible** under 2012-2019 positive net, PF>1, >=100 trades. Chosen RSI7 OS25 OB80 H4 inverse: training **36/96 profitable months and +$37.88/oz**; previously exposed 2020–Sep2026 **26/81 and -$193.03/oz**.
- Stochastic audit: **96,254 simulated trades across 12 overlapping configurations**, **zero** design-eligible.
- Against existing carry-gap MACD H4 selected and previously researched FVG H4 strong benchmark (2020–Sep2026 = 81 months, last month partial): FVG H4 strong **2oz** returned **50/81 positive months +$1739.37**; MACD selected **2oz** **44/81 +$1613.05**; FVG1oz+MACD1oz **46/81 +$1676.21**. Alternative FVG1.5oz+MACD0.5oz resulted **51/81 +$1707.79**, but this was screened *after* historical period had been seen and is NOT a new deployable selection. FVG1oz+MACD0.5oz+RSI0.5oz **47/81 +$1176.44**.
- **Twelve** exposed months where FVG, MACD and RSI all had <=0 net per 1oz: `2020-10, 2021-07, 2021-08, 2022-01, 2022-04, 2022-06, 2022-11, 2024-01, 2024-06, 2025-05, 2025-07, 2026-07`. These cannot be rescued by any static nonnegative blend of those three exact monthly PnL streams.
- Monthly ledgers recomputed directly from every RSI/Stoch trade. Maximum absolute ledger-to-monthly difference <= **$0.00000054** due to CSV rounding. Does not independently certify trade fill realism.
- Full reports in conversation: `NoRiskFX_Monthly_Profit_Search_Gap_Corrected_2026-10-25.xlsx` (START_HERE, MODEL_RESULTS, MONTHLY_177, 12_COMMON_RED, METHOD_AND_LIMITS); full reproducibility files (scripts, CSV, trades, audits excluding raw market data) in `NoRiskFX_Monthly_Profit_Research_Checkpoint_2026-10-25.zip`.

## Research interpretation

No tested strategy here made money in **every single month**. A perfect 81/81 result would be suspect given extensive prior inspection of 2020–2026. Monthly cash-flow smoothing, hindsight rotation or posthoc weight selection does not prove forecasting ability or guarantee future profits. Many indicator studies before this fix forcibly exited trades at normal quote breaks and must not be compared without execution-policy reconciliation.

**Important outstanding flaws:** RSI/Stoch and some older MACD source TF aggregation may retain partially observed H1/H4 candles despite signal adjacency conditions; still needs a strict full-candle qualification and independent trade-by-trade parity on frozen central engine. Unobserved intra-gap ticks and floating worst excursions are not known. Independently backtesting 3 concurrent 1oz strategies and summing monthly PnL does NOT impose shared margin, correlated exposure, worst combined open drawdown or real concurrent execution.

## Next high-priority acceptance gates

1. Fix central-engine GitHub Actions bootstrap after account allowance renewal **2026-11-01** (account exhausted 2,000/2,000 Actions minutes and 0.5/0.5 GB Actions storage in Oct 2026); workflow triggers are temporarily manual-only, Issue #2 tracks billing/quota. Never change payment settings.
2. Enforce full completed H4/H1 swing bars and audit all model entry timestamps/SL-TP chronology under a SINGLE simulator.
3. Pre-register a genuinely distinct market-regime or microstructure hypothesis on only historical **2012–2019**, then evaluate older 2020–2026 as already exposed sensitivity, and use truly new forward data for independent confirmation.
4. Build a simultaneous-position capital/margin ledger and report weekly/monthly **realized AND mark-to-market equity** and risk of ruin, not just count of positive months.
5. Do not promise 81/81 monthly income or real-trading profitability.

