# NRF-FAC-002 — preregistered Donchian breakout FADE

**Committed before reading any FAC-002 real XAUUSD yearly performance:** implementation `scripts/batch_channel_fade_grid.py` at commit `4188ed961826e4e044a81a70a3aab740427a8136`.

## Hypothesis, frozen specification and intended scale

FADE the *same* fully closed M15 Donchian breakout events used by FAC-001, rather than following them: when the prior M15 channel is broken upward at an M15 candle close, enter short at next eligible M1 open; for downward break, enter long. This is a countertrend hypothesis, not merely shifting the lookback in the previous trend-following family.

20 prior channel lookbacks 5–24 × 25 stop distances $1.00–$13.00 in $0.50 increments × 40 profit targets $1.00–$20.50 in $0.50 increments = **20,000 predeclared strategy specs per calendar year**. **Test both 2012 and 2013**, annual separate resets, original private Gold data.zip SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`; 40,000 potential genuine yearly backtests but count only fully completed runs. The original source data is **NEVER** uploaded to public GitHub.

Stop-first M1 BID-reference OHLC, adverse open gap-through, next eligible M1 open no later than 1 minute after confirmed M15 candle close, one position, 1 ounce, exactly $0.40 USD/oz full-cycle ALL-IN roundtrip, no additional spread/commission/slippage. At least three parameter samples per annual batch must exactly match source engine `run_fast` for trade counts, annual and monthly P/L, fees and observed floating maximum drawdown within 1e-7. Explicitly reject fills beyond available observation or ambiguous after-market-close execution.

## Interpretation gate

All 2012–2013 years were exposed to related prior strategy searches, and selecting the highest score from 20,000 highly correlated configurations is severe multiple-comparison bias. **No candidate is promoted as truly independent or live-ready** merely for positive annual P/L or 12/12 historical positive months. Compare exact parameter IDs across both years (never pair unrelated yearly winners). Distinguish native strategy hypothesis count (one family) from parameter counts (20,000 specs), and annual simulation count (up to 40,000) honestly.

Required outputs: full 12-month per-variant realized net after fee, 1-ounce floating M1 max drawdown, worst month, number of months positive, total trades and fees, candidate spec, SHA fingerprint. Save without raw market quotes.

Goal is to reject failed families quickly and expand research to genuinely distinct next hypotheses (EMA variations, mean reversion, liquidity/regime multi-timeframe, etc.) and eventually evaluate *shared-capacity, non-overfitted* composites; the goal of sustained monthly profits is an aspiration, **not a guarantee**.
