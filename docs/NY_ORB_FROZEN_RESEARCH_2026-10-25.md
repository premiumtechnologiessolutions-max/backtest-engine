# NY opening-range hypotheses — frozen one-pass evaluation 2026-10-25

**Research outcome: reject both candidate variants based on 2012–2019 pre-exposure design.** No tuning using previously exposed 2020–September 2026 data.

## Source and fixed execution

Original private XAUUSD Gold data.zip (2012–2026 M1 BID/ASK); SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. The raw archive is not committed to GitHub.

- America/New_York DST-correct clock. Opening-range research window **08:30–08:59 NY**, requiring all **30 consecutive M1** candles.
- Event window 09:00–11:59 New York, max 1 intraday trade per day **per model**, no overnight exposure (flat by 15:59 NY).
- **Breakout:** cross upper/lower range by $0.10; buy/sell at threshold or adverse first candle open; stop behind opposite range boundary by $0.10.
- **Failed breakout (fade):** wick sweeps boundary at least $0.20 then closes back inside; enter counter-direction next available adjacent M1; stop $0.10 beyond sweep candle extreme.
- Both require risk within $2–$25 per oz, target 1.5R, **fixed ALL-IN $0.40/oz per completed trade**. M1 OHLC SL-first ambiguity, no fake intragap fills. The $0.40 is subtracted once and no extra variable spread/commission is added.

**These are predeclared fixed hypotheses**, not an optimized ORB family. The 08:30 NY opening-range label is a research time window, not the opening of the 24-hour global gold market.

## Results

| Fixed hypothesis | Design 2012–2019 positive months / 96 | Design net (1oz) | Already-exposed 2020–Sep2026 positive months / 81 | Exposed net (1oz) |
|---|---:|---:|---:|---:|
| NY_ORB30_breakout_R1p5 | 36 | **−$397.16** | 35 | **−$492.82** |
| NY_ORB30_failed_break_fade_R1p5 | 19 | **−$15.02** | 29 | **−$92.12** |

Full 2012–Sep2026 observations: **3,346 breakout trades** (−$889.98/oz total) and **413 failed-break fades** (−$107.1375/oz total). All weekly/monthly/yearly aggregates reconcile to source executed-trade net P/L to below 0.0001 USD. Dates 2026-09 incomplete.

The scripts/ledger/audits exist in conversation artifact `NoRiskFX_NY_ORB30_Frozen_Hypotheses_2012_2026_2026-10-25.zip` (9 files including full standalone source, trades, weekly.csv, monthly.csv, yearly.csv, annual quality, period metrics, audit JSON and Arabic research report). **No raw ZIP is included**.

## Decision and status

Do not deploy or weight these models into a portfolio simply to improve monthly positivity. Both failed 2012–19 eligibility. These 2020–26 results are **historically exposed, NOT independent prospective or clean OOS**. The standalone research driver has not been integrated as a certified central-engine GitHub strategy; this is a reject/negative-control archival case.

In parallel, strict H4 bar completion revalidation showed that **3,613/23,230** legacy H4 bars were partial and frozen MACD_H4_zero1_RR2 original declined from design **55/96** to **46/96** positive months and exposed **44/81** to **39/81**; see `docs/STRICT_H4_REVALIDATION_2026-10-25.md`. This means earlier combined FVG/MACD profitability should not be treated as audited until a single central full-candle policy is used everywhere.

**GitHub Actions** is account-quota blocked until 2026-11-01; the owner already received GitHub official 100% minutes and storage notifications. Runner tests have NOT passed; PR #1 remains draft.
