# NRF-FAC-003 — preregistered complete-M15 wick-rejection hypothesis

**Frozen before opening any FAC-003 original-gold historical results** (2026-10-26). Implementation: `scripts/batch_wick_rejection_grid.py`; synthetic tests: `tests/test_batch_wick_rejection_grid.py`.

**Distinct entry logic from FAC-001 Donchian trend and FAC-002 Donchian fade, RSI, EMA crossover, NY opening range, compression breakout, or H1 BOS:** an M15 candle with a dominant rejection wick and strong close at the opposite edge is treated as a rejection signal. Uses only the current **fully completed M15 candle**. No channel lookback, no future candles, no volume proxies.

At the M15 candle **close_at**, compute body=max(abs(close-open), $0.10), upper=high-max(open,close), lower=min(open,close)-low, span=high-low. For LONG: span≥minrange, lower≥wick_body*body, lower≥1.5*upper, close-low≥0.65*span. SHORT symmetric: upper≥wick_body*body, upper≥1.5*lower, high-close≥0.65*span. No dual-direction signals. Incomplete M15 bars are discarded; signal timestamp is candle close and can only fill next available M1 open within one minute.

**Frozen grid:** 12 wick/body ratios 0.50..3.25 by 0.25 × 6 minimum M15 candle ranges [0.75,1.50,2.25,3.00,3.75,4.50] USD/oz × 20 stops 1.00..10.50 by 0.50 × 20 targets 1.00..10.50 by 0.50 = **28,800 parameter specifications per year**; **2012 and 2013** original-source years, 57,600 potential annual backtests (count only actual completed). These variants are highly correlated; log actual distinct entry signal sequences and zero-trade variants. This is ONE entry hypothesis family, not 28,800 independent strategies.

**Execution contract:** original private `Gold data.zip` SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` stays private. One ounce, one position, next available M1 open <=60s after M15 close, full-roundtrip $0.40 USD/oz ALL-IN, stop-first on ambiguous BID M1 candles, adverse gap-through open fills, year-end forced close and annual reset. No invented missing minutes or broker tick claims.

**Validation:** `replay_core` event replay on original M1 data, then at least 6 deterministic full `run_fast` reference samples per year verifying monthly settled net, trade count, fee, total net, and minute-marked floating max drawdown to 1e-7. Synthetic CI parity tests including missing minutes and rejection direction. Log every parameter's 12 UTC monthly settled P/L, positive-month count, worst month, fees, trades, max M1 floating drawdown, and original source fingerprint. Avoid any ranking that rewards zero-trade months. Compare **same immutable parameter ID** across years.

**Evaluation status:** Both 2012 and 2013 were historically exposed to other research, so this is NOT independent OOS even if 12/12 or 24/24 months is discovered by post-hoc grid search. Do not infer future profitability or initiate live trades. Freeze the family and grid before viewing results; reject negative outcomes honestly.
