# First continuous real-data backtest smoke audit — October 25, 2026

**Status: executed with a separate local Python M1 reference runner; GitHub PR engine has not yet passed its CI or completed an independently verified parity replay.**

Historical dataset: private `Gold data.zip`, SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. BID/ASK M1 source; **no real ticks**. Do not commit the raw ZIP.

## Frozen research fixture (not a trading recommendation)

- Donchian price channel H1 breakout: close of a fully observed H1 candle above previous 20 H1 highs or below previous 20 lows; no lookahead.
- Market enter at next M1 open when no position already exists. One position at a time, no pyramiding.
- **Fixed stop $15 per ounce of XAUUSD price** and target $30; this is **not** the classic Turtle 20/10 full system.
- Position can span days and years; gap is not an automatic exit. When opening beyond stop, exit at next observed opening price. If SL and TP both inside an M1 bar, SL assumed first.
- Cost is **exactly $0.40 ALL-IN per ounce per completed trade**; no additional spread/commission/slippage.
- One ounce per trade and common BID-derived research-price reference; not broker-executable Bid/Ask fills.

## Executed observation — 2020-01-01 to 2026-09-20 (partial September)

| Metric | Result |
|---|---:|
| M1 observations | 2,381,928 |
| Generated closed-candle breakout signals | 4,122 |
| Completed trades | 1,334 |
| Months in report | 81 |
| Profitable months | 48 |
| Total realized net USD (1 oz) | +1,146.00 |
| Worst month | -208.60 |
| Max observed minute-close drawdown | 637.76 USD |
| Reference execution loop time (after loading) | 2.73 seconds |
| Tick fills validated | **No** |
| Clean independent held-out test | **No** |

Per-year accounting from the same continuous run:

| Year | Profit-positive months | Net USD |
|---|---:|---:|
| 2020 | 8/12 | +464.60 |
| 2021 | 5/12 | -289.60 |
| 2022 | 6/12 | +54.99 |
| 2023 | 8/12 | +73.63 |
| 2024 | 6/12 | +141.20 |
| 2025 | 8/12 | +484.98 |
| 2026 until Sept 20 | 7/9 | +216.20 |

The audited standalone artifacts in the ChatGPT conversation are `NoRiskFX_Engine_RealData_Smoke_2020_2026.zip`, containing source scripts, trade ledger, weekly/monthly CSVs, equity daily and JSON source fingerprints. **Not uploaded into the repository**.

Internal arithmetic checks completed for that standalone run: `sum(trades.net)==sum(weekly.net)==sum(monthly.net)` tolerance <1e-6; exactly $0.40 cost per trade per one ounce; no trade closes before entry. These checks do NOT prove the GitHub execution module matches; `tests/test_fast_engine.py` documents required fast-versus-reference parity pending runner execution.

## Run central GitHub engine (once dependencies and runner work)

For one year directly from the private ZIP:

```sh
norisk backtest --data "/secure/Gold data.zip" --start 2024-01-01 --end 2024-12-31 --strategy donchian --execution fast --timeframe H1 --donchian-lookback 20 --stop-usd 15 --target-usd 30 --ounces 1 --all-in-cost-per-ounce 0.40 --out reports/generated/donchian-2024
```

If the run produces a different trade ledger than the reference replay, **freeze the result as a regression failure** and fix the engine before interpreting the strategy.

## Blocking tasks before "ready"

1. Github Actions run `40208708790` for **runner-only** workflow failed within 2 seconds with **0 steps and runner_id=0**; standard CI also fails. This indicates job was not assigned to a runner. Cause is unverified (could be GitHub billing, policies, platform or account Actions permissions). No GitHub Actions success can be claimed.
2. Run `pytest` inside a usable execution environment against the exact current GitHub commit, then compare old `execution.run` with `fast_engine.run_fast` at trade and equity level.
3. Run the exact integrated `norisk backtest` CLI and compare every real 2024 Donchian trade to this baseline (not just PNL).
4. Real tick execution, authentic Bid/Ask fill parity with MT5, portfolio margin ledger and FVG limit-order engine are NOT implemented.
5. Previous 2020–2026 outcomes are previously exposed and cannot be declared clean out-of-sample. Future prospective data will be needed.

## Follow-up gate (2026-10-25, after FVG foundation)

The central engine now rejects **per-minute realized P/L timeline drift**, even
when final trade net, final equity, and the floating-equity arithmetic still
match. See `src/norisk_quant/accounting.py` and regression tests in
`tests/test_accounting_integrity.py`. These new tests are committed but
**not certified passing**, because the GitHub Actions runner remains unavailable.

A new **real-year parity command** runs the exact installed repository
package against the user's private source archive:

```bash
python scripts/parity_donchian_year.py --zip "/secure/Gold data.zip" --year 2024 --out reports/generated/parity-2024.json
```

It compares every trade column, each observed M1 equity sample, signal
pending/expiry counters, and fixed-cost accounting for reference versus fast
execution. It fails with exit code 1 on any difference, emits source SHA-256,
and does not send market data to GitHub. It **has not yet been run** on the
current GitHub commit. This is an *internal two-kernel parity check* and
does not prove agreement with the independent 2024 standalone script,
broker tick fills, or multi-year carry at the year boundary.

**Latest runner evidence:** GitHub Actions runs `40212582381` and
`40212582476` again failed before observable job steps. Issue #2 remains
open. Draft PR #1 must remain unmerged until independent executable tests
and CI can be observed passing.
