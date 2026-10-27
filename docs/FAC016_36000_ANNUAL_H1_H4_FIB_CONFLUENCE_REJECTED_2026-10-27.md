# FAC016 — Frozen H1/H4 Fibonacci confluence: 36,000 completed annual M1 replays (REJECT)

**2026-10-27. Historical design years 2012–2013 are exposed, not clean OOS.** The hypothesis, 18,000 correlated parameter specifications and acceptance criteria were frozen before original-data outcomes at [721387e](https://github.com/premiumtechnologiessolutions-max/backtest-engine/commit/721387e06a81cfd47e0e33d5b31815a3dd6b0e96). The earlier H4 pivot-width feasibility amendment is preserved in [the frozen specification](FAC016_FROZEN_H1_H4_FIB_CONFLUENCE_2026-10-27.md); no result-driven grid alteration.

## Data and execution audit

- Private original `Gold data.zip` SHA256 verified locally: `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. **Never uploaded raw BID/ASK quotes to this public repository or GitHub Actions.**
- Local reproduction of the already committed `scripts/batch_h1_h4_fib_confluence_grid.py`, using an earlier GitHub CI-source snapshot whose **core dependency blobs were verified identical to the current branch**: `fast_engine.py` 08b291c4a2e24625e047862440bfb2f588729078, `batch_compression_h1_grid.py` 1a05dcecfd11e8e9ff4502b21325445fe7182983, `data.py` 366af69961dbf31f40ac5bde53674d5f949b4dc7, `strategy.py` 5ce53a4542474bd36804f6d2c0d3af8ee8cfcef0. **The local FAC016 runner is a manual transcription, not an independently verified byte-identical official checkout**; exact-head official full-grid reproduction remains a separate audit item.
- Completed H1/H4 pivot confirmation only after right-side bars close; fully observed UTC-anchored H1/H4/M15 candles, no fabricated minutes, local London/New York DST masks, next observed M1 open <=60s, one position, stop-first, adverse gap-through, exactly **$0.40/oz ALL-IN roundtrip only**. Exit-booked UTC months; M1 floating equity drawdown.
- 18,000 correlated parameter IDs per year, not 18,000 independent hypotheses; 180 pre-execution signal-rule combinations (fewer unique signal streams after duplicate/empty signals).

## Complete grid — negative result

| Metric | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Completed annual parameter replays | 18,000 | 18,000 | **36,000** |
| Active annual replays (>=1 filled trade) | 17,000 | 14,300 | **31,300** |
| Zero-trade annual controls | 1,000 | 3,700 | **4,700** |
| Exit-booked monthly values incl zero-trade | 216,000 | 216,000 | **432,000** |
| Active monthly values | 204,000 | 171,600 | **375,600** |
| Annual-net-positive parameter executions | 6,108 | 3,352 | 9,460 |
| Maximum positive months within one year | 10/12 | 9/12 | **17/24** for same ID |
| Unique hashed signal streams | 169 | 131 | Correlated |
| Canonical `run_fast` parity samples | 4 | 4 | **8** |

- **1,027 / 18,000** exact parameter IDs showed positive net in **both** design years.
- **0 / 18,000** achieved >=18/24 positive months; **0** achieved 24/24; **0** passed the preregistered joint gate (>=80 fills each year, >=18/24 positive months, annual net >0 both years, worst month >=-$20/oz, max annual observed M1 floating DD <=$100/oz).
- **1,210 / 18,000** met the minimum >=80 fills/year independently of the other criteria. **13,800** IDs traded in both years.
- All annual net/12 monthly values and `fees = $0.40 * filled trades` reconciled numerically. **REJECT**. No post-result threshold changes.

## Most positive months — post-hoc diagnostic, NOT a recommendation

`FIB16_H2_H41_F0.620_T1.50_ALL_SL2.00_TP2.50`

| Year | Positive months | Net after fee /oz | Trades | Fee /oz | Worst month /oz | Max annual M1 floating DD /oz |
|---|---:|---:|---:|---:|---:|---:|
| 2012 | 8/12 | +$60.2975 | 96 | $38.40 | -$15.4275 | $36.9600 |
| 2013 | 9/12 | +$40.2325 | 89 | $35.60 | -$35.5475 | $48.0600 |
| **Two separate annual resets** | **17/24** | **+$100.5300** | **185** | **$74.00** | **-$35.5475** | **$48.0600 max annual** |

**Monthly exit-booked net $/oz (January–December)**

- **2012:** +20.1450, +6.9325, +11.9625, +17.8925, +10.8550, +11.9150, +2.4825, -6.1200, -4.2775, +3.9375, -15.4275, 0.0000.
- **2013:** -4.5250, -8.6525, +1.1000, +14.9750, +34.3325, -35.5475, +3.8450, +4.6175, +16.6400, +3.5300, +6.7875, +3.1300.

This top-by-month-count candidate **fails** the frozen worst-month >=-$20/oz requirement and the >=18/24 month criterion. Its 17/24 selection is highly post-hoc.

## Parity and limits

- **8** local `run_fast` samples across both years matched the JIT bulk executor's monthly values, fees, fills and observed floating M1 DD (reported zero differences).
- The 17/24 diagnostic underwent **2 complete independent slow `execution.run` vs `run_fast` reference replays** on the authenticated private original data: **185 trades, every trade field and all 705,292 observed M1 equity marks identical**, including all 24 monthly outcomes.
- Historical 2012/2013 were previously exposed; these are *not* 36,000 independent hypotheses, clean holdout results, a broker tick model, or evidence of monthly-profit guarantees. No shared-capacity multi-strategy portfolio is inferred from summing independent annual profits. No live trading.
- Full per-ID monthly results and parity JSON were generated locally and retained in a separate downloadable research ZIP, **not raw quotes**. They have not been committed as 10MB+ public CSVs.
- GitHub Actions CI for this results-documentation commit must be checked after commit. Previously verified exact head 0320aaa7 passed **795 tests** on run 40433338540; that is not a claim that the new results commit has passed.

**Decision:** FAC016 **REJECTED**. Do not re-fit this family to already observed years. Reserve any future forward/prospective data for a truly frozen model with embargo and multiple-testing correction.