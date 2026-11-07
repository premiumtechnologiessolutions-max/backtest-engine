# No Risk FX high-throughput research registry — 2026-10-26

This is the canonical **do-not-repeat** index for the 2012–2013 original-source high-volume campaigns. Always check it and each frozen design before generating a new experiment. Keep branch `feat/quant-engine-foundation` and Draft PR #1 unmerged.

| Research ID | Signal family | Unique correlated parameter specs | Completed yearly backtests | Settled monthly entries | Max positive months of 24 | 24/24 | Disposition |
|---|---|---:|---:|---:|---:|---:|---|
| NRF-FAC-001 | M15 Donchian **follow breakout** | 20,000 | 40,000 | 480,000 | 16 | 0 | REJECT 24/24 target |
| NRF-FAC-002 | M15 Donchian **fade breakout** | 20,000 | 40,000 | 480,000 | 18 | 0 | REJECT 24/24 target |
| NRF-FAC-003 | M15 **rejection-wick** price action | 28,800 | 57,600 | 691,200 | 18 | 0 | REJECT 24/24 target |
| **Total** | **3 distinct entry families** | **68,800** | **137,600** | **1,651,200** | — | **0** | **NO validated winner** |

**Do not count 137,600 as 137,600 independent strategies**: it is 68,800 correlated parameter specs replayed separately in two historically exposed years. The Donchian follow/fade entries share underlying channel event triggers; thus even the three families are not statistically independent in a strict sense. Each year's runs reset positions and close at year end; these are not continuous two-year equity curves. No clean OOS.

**Portfolio negative control NRF-FAC-P01:** predeclared Donchian L10 SL5 TP10 + M15 wick ratio1.5 minrange3 SL5 TP10, wick-first tie priority, one **shared** position. 2012 -$401.18/oz (2/12 months positive); 2013 -$485.34/oz (2/12). Entire 1,820 shared-capacity trade ledger and 705,292 original M1 equity marks matched independent reference `execution.run`. **REJECT**. No additive accounting of separately replayed strategies.

**Code and evidence:** `scripts/batch_donchian_grid.py`, `scripts/batch_channel_fade_grid.py`, `scripts/batch_wick_rejection_grid.py`; `docs/FAC001_BATCH_40000_RESEARCH_2026-10-26.md`, `docs/FAC002_BATCH_40000_RESEARCH_2026-10-26.md`, `docs/FAC003_BATCH_57600_RESEARCH_2026-10-26.md`, `docs/FAC_P01_SHARED_PORTFOLIO_REJECTED_2012_2013_2026-10-26.md`. Public CI code at `https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40384924105` passed 611 tests; original M1 quotes are **never uploaded**. Original ZIP SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.

## Next autonomous research work (not yet counted as completed)

1. Propose a **genuinely distinct causal hypothesis** beyond Donchian follow/fade, RSI M01, EMA cross, wick rejection, opening-range ORB01, compression CEB01, NYM01, BOS, FVG and previously tested session regimes. Freeze its thresholds, timing and risk model **before** reading new results.
2. Use one shared event-replay kernel with per-variant **12 monthly net** values, worst month, fees, M1 floating drawdown, trade count, observed-month coverage, original data fingerprint, and distinct entry-signal hashes. Run thousands to tens of thousands of variants where compute permits. Do not count a generated spec until executed.
3. Verify at least several original-data candidate samples against canonical `run_fast` (net, monthly, fees, trade count, floating DD). For any selected composite, use `run_fast` with one shared position capacity and verify **complete ledger and every M1 equity mark** against reference `execution.run`.
4. Penalize multiple testing, lookahead, annual resets, no-trade months, large negative tails and quote costs. If results are promising, freeze candidates and reserve genuinely unobserved evaluation periods or future forward tests. **2012–2013 are historically exposed, NOT OOS**.
5. Save both negative and positive exploratory results, commit code/docs and keep Draft PR open. A scheduled hourly ChatGPT run is **not** a persistent cloud worker or automatic live-trading service.

**Safety:** no live orders, no billing/privacy changes, no raw market data in GitHub/CI, no promise of 12/12 profitable months.
