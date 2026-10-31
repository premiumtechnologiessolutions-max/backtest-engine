# NRF-FAC-005 — invalidated by observed H1 session gaps (2026-10-26)

**Decision: REJECT AS NON-EXECUTABLE on this source, not a profitable or losing strategy.** No original-data parameter retuning; the preregistered [FAC005 hypothesis](FAC005_FROZEN_H1_ATR_M15_EMA_2026-10-26.md) remains frozen and unchanged.

The exact GitHub CI source commit `d6a86702d99602cd504937cccece5880a6577c9f` passed **637 pytest tests** and installed synthetic CLI smoke at [GitHub Actions #40388310669](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40388310669). Its packaged source artifact was executed against the original private `Gold data.zip`, SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`, **without uploading raw market data**.

The **frozen requirement of 39 consecutive fully observed H1 transitions (40 consecutive complete H1 bars)** is impossible on the observed original 2012–2013 feed because the daily quote session interruption breaks H1 continuity. This is not a code failure or an excuse to alter a frozen result:

| Observation | 2012 | 2013 |
|---|---:|---:|
| Original observed M1 candles | 352,975 | 352,317 |
| Complete H1 candles | 5,600 | 5,486 |
| Maximum consecutive complete H1 bars | **23** | **23** |
| Regime-qualified H1 bars (ATR/median available) | **0** | **0** |
| Distinct signal sequences across 64 rule variants | **1 (all empty)** | **1 (all empty)** |
| Actual parameter evaluations | 25,600 | 25,600 |
| Parameter variants with any filled trades | **0** | **0** |
| Canonical `run_fast` comparisons | 6 zero-trade parity checks | 6 zero-trade parity checks |

The code **did run 51,200 parameter executions**, but **all 51,200 were zero-trade**. They MUST NOT be described as 51,200 meaningful strategy backtests, nor combined with previously active backtests as evidence of strategy profitability. This is a **data-coverage incompatibility negative control**. Six zero-trade parity checks per year are not evidence of filled-order parity. The experiment generated 614,400 month slots with zero trades, not observed trading outcomes.

**Future experiment design:** If the goal remains testing an H1 volatility regime, preregister a separately labeled new hypothesis with a gap-aware statistic that consumes only fully observed H1 bars, explicitly distinguishes scheduled quote interruption from missing candles, and never invents absent prices. That new hypothesis would be an adaptive, historically exposed *follow-up*, not independent OOS or retroactive success for FAC005. Prefer real filled-trade evidence and fresh prospective evaluation. No live deployment.
