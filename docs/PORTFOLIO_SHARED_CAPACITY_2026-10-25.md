# Shared-capacity portfolio research kernel — 2026-10-25

**Development-only.** Added `src/norisk_quant/portfolio.py` and `tests/test_portfolio_shared.py` to the SAME private repository and Draft PR #1. The module is not connected to the existing `norisk backtest` CLI yet, and is NOT a broker-margin simulator.

## Why this was necessary

Summing historical monthly profits from independently executed FVG, MACD, RSI, etc. cannot demonstrate whether they could actually coexist within one account. The new `run_portfolio(minutes, signals, settings)` evaluates all market-entry signals on **one observed M1 timeline**, with simultaneous positions and a **shared cap** on both position count and gross open ounces.

- Frozen per-strategy ounce allocations; no dynamic selection using future months.
- Deterministic signal priority: confirmation time, then strategy ID, then input order.
- One position per strategy, configurable maximum concurrent positions and gross open ounces.
- Capacity is frozen at minute open: a position closing during this minute cannot immediately free a slot for a new signal in that same M1 bar.
- Signal confirmation must not occur after entry; stale signals expire; signals blocked by capacity or duplicate open strategy are counted separately.
- Carry positions across observed data gaps; adverse first-observed opening-price gap-through stop. Stop-first if SL and TP are both touched in the same M1 OHLC candle.
- **Exactly $0.40 USD ALL-IN per ounce per completed roundtrip**, charged once (not an extra variable spread or commission); open-position mark-to-market accrues that single expected fee.
- Single realized and floating equity timeline, gross open ounces and position count on every observed M1.
- `validate_portfolio` rejects double fees, P/L miscalculation, per-strategy overlapping trades, capacity breaches, and realized-P/L timeline shifts.
- `write_portfolio_report` produces trade, M1 equity, weekly/monthly **realized vs. mark-to-market** CSVs and a JSON summary.

## Executed local verification, not GitHub CI

In a separate local Python environment, the **same 15,033-byte portfolio module** was tested with a simplified local copy of the Signal dataclass (NOT a full checkout of the current GitHub repository). Six isolated pytest tests passed:
1. Two simultaneous strategies, shared equity and single fee per roundtrip.
2. Shared position capacity and no same-minute slot recycling.
3. 18-minute missing-data gap and adverse open stop.
4. Double-fee and realized-booking-time corruption detection.
5. Future signal cannot enter, and unknown strategy allocation is rejected.
6. Month boundary with unrealized January P/L and realized February P/L.

Additional local smoke used **2,758 actual 2024 M1 rows**, from 2024-02-05 through 2024-02-06 in private `Gold data.zip` SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Two artificial, opposing one-ounce fixture signals generated **2 completed trades**, combined **-$14.74** net, exactly **$0.80** total fees and a maximum of **2 open ounces**. The accounting check passed. These deliberately artificial trades are **not** a profitability study, and no old 2020–2026 backtests were repeated.

The local reproducibility ZIP is attached in the conversation as `NoRiskFX_Portfolio_Shared_Capacity_Local_Verification_2026-10-25.zip`; original gold data is not included or committed.

## Remaining acceptance gates

1. Run the **exact installed GitHub revision** and all repo tests when GitHub Actions quota permits or a trusted complete local checkout becomes available. The 6 local module tests **do not mean CI passed**. Actions quota reset expected 2026-11-01, Issue #2; do not change billing.
2. Integrate a dedicated CLI command/config file with explicit per-strategy sizing and run true concurrent Donchian/EMA then FVG limit orders. This first portfolio kernel supports **market-entry Signal** only, not concurrent pending limit orders.
3. Test portfolio trade-by-trade against a separate independently coded reference, verify multiple-year continuous replay and the original M1 source schema.
4. Add broker-specific contract/margin, maintenance margin, forced liquidation and intrabar exposure bounds; current gross-ounce cap is **not** actual capital or margin.
5. Run only preregistered strategies with 2012–2019 selection. All 2020–2026 data have been exposed in earlier research and are **not independent OOS**. No 81/81 monthly claim, no live trading.

**Do not merge Draft PR #1** without complete independent tests and CI evidence.
