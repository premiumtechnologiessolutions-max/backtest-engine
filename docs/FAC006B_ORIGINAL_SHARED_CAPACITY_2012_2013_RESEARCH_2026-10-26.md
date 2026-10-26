# NRF-FAC-006B — original-source shared-capacity portfolio: ENGINE PASS, STRATEGY REJECT (2026-10-26)

This is a **separately frozen** [FAC006B engineering follow-up](FAC006B_FROZEN_CANONICAL_PENDING_SHARED_PORTFOLIO_2026-10-26.md) after [FAC006 original 2012 parity failed](FAC006_ORIGINAL_2012_PARITY_BLOCKER_2026-10-26.md). **In-sample**, not clean OOS, no live trading recommendation.

## Source and execution
Exact GitHub source commit `a1a7d46412a10022c5494868c84ddc7abbef16c2` passed **660/660 pytest**, CLI smoke and end-to-end smoke at [Actions #40390397630](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40390397630). That exact CI source artifact was executed offline on private original `Gold data.zip`, verified SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. **No raw BID/ASK quotes uploaded** to GitHub.

FAC006B uses `PortfolioSettings.defer_same_strategy_market_signals=True` **only as an explicit opt-in**. The existing default `False` retains conservative immediate rejection. A fully confirmed same-strategy Market signal can wait for the next observed M1 open if within 60 seconds, never recycle same-minute capacity, and cannot displace another strategy's occupied shared slot. Stop-first, adverse observed gap-through, 1-oz per strategy, $0.40/oz ALL-IN roundtrip, separate yearly reset.

Three immutable components: `A_RANGE_SLOW` FAC005B EMA8/72 H1 range gate1 SL6.5 TP1; `B_RANGE_FAST` EMA16/26 gate0.8 SL8 TP10; `C_RSI_BASE` FAC004 RSI14 lower threshold30 SL4 TP4. **Two range components were selected after seeing these same years' outcomes**, so portfolio performance is selection-biased.

## Three-slot canonical control: exact original-source PASS

With three shared slots / 3 ounces maximum, compared against **three independent canonical `run_fast`** references on the same observed M1 rows. Filled counts, fees, all 12 monthly P/L values, and **every observed M1 equity mark** matched to tolerance 1e-7.

| Control | 2012 | 2013 |
|---|---:|---:|
| Observed original M1 rows | 352,975 | 352,317 |
| Canonical trades | **739** | **715** |
| Three-slot trades | **739** | **715** |
| Max monthly net difference | 6.22e-14 | 9.95e-14 |
| Max M1 equity difference | 7.67e-13 | 1.28e-12 |
| Capacity rejects | **0** | **0** |
| Three-slot net after fee ($/oz accounting units) | **-$112.89** | **-$289.93** |

Three-slot is a **3-ounce exposure control**, not the executable one-ounce shared portfolio.

## One-slot / one-ounce shared portfolio: actual results

All three generators compete for one position slot, max 1oz total, deterministic priority. No independent P/L summation. `validate_portfolio` passed all fee, chronology, shared capacity and realized/floating accounting checks.

| One-slot metric | 2012 | 2013 |
|---|---:|---:|
| Filled trades | **601** | **583** |
| Positive exit-booked months | **6/12** | **4/12** |
| Net after $0.40/oz ALL-IN fee | **-$50.69** | **-$189.89** |
| Worst month | -$76.80 | -$115.61 |
| Max observed annual M1 floating DD | $214.74 | $206.24 |
| Capacity-rejected signals | 173 | 161 |
| Duplicate same-strategy rejections | 238 | 193 |
| Max simultaneous positions | **1** | **1** |

Across **two separately reset annual accounts**: 1,184 trades, **10/24 positive months**, summed net **-$240.58/oz**, 334 shared-capacity rejects and 431 duplicate rejects. This is **NOT** a continuous 24-month financed account, and the annual M1 drawdowns must not be combined into an invented continuous DD.

Full private reproducibility bundle `NoRiskFX_FAC006B_2012_2013_Shared_Portfolio_Verified_2026-10-26.zip` contains both years and both modes: exact CI source, SHA256 manifest, frozen spec, original loaded-source fingerprint, trades, weekly/monthly/strategy attribution, complete M1 marked equity, accounting audit and 24-month comparison. **No raw quotes.**

**Decision:** FAC006B engineering acceptance **PASS**; this three-component strategy portfolio **REJECT** for monthly consistency. Historic design-year selection and M1 OHLC synthetic fills are not broker-tick forward proof. Do not deploy live.
