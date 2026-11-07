# NRF-FAC-005 — FROZEN before historical outcomes: H1 relative ATR expansion gated M15 EMA crossover

**Freeze date:** 2026-10-26 UTC. **Status:** predeclared; not a profitable-strategy claim. GitHub source commit of this document predates FAC005 original-data results. No tuning after inspecting any FAC005 results.

## Different causal hypothesis
A completed M15 fast/slow exponential-moving-average **cross** can be traded only while the latest fully closed H1 candle shows a *high relative volatility regime*: H1 14-bar simple-average true range (ATR14-SMA) divided by the median of the **24 prior completed H1 ATR14-SMA values** is at least the threshold. This tests volatility-expansion-confirmed trend initiation rather than Donchian, wick rejection, or RSI recross. **No future H1 data, no incomplete H1 or M15 candle**.

- M15 fast EMA spans: **5, 8, 12, 16**; slow EMA spans **26, 34, 50, 72**; each pair fast < slow.
- H1 relative ATR14 / previous-24 ATR median gate: **0.80, 1.00, 1.20, 1.40**.
- Exactly **64 causal signal-rule parameter specs per year** (4×4×4). Each ×20 stop distances **$1.00, $1.50, ..., $10.50 per oz** ×20 targets of the same distances = **25,600 candidate trade parameter specifications per year**.
- EMA crosses up from fast<=slow to fast>slow => long; crosses down from fast>=slow to fast<slow => short. Fully closed M15 only. EMAs reset at M15 gaps, require at least slow+2 consecutive complete M15 candles in the current uninterrupted run.
- H1 TR needs prior contiguous H1 close; ATR14-SMA is a rolling mean of 14 valid H1 TRs; prior-24 median excludes current H1 ATR. H1 regime gate also requires at least 40 contiguous complete H1 candles (39 contiguous transitions). If the latest H1 close is older than 60 minutes at M15 confirmation, skip. Latest H1 closed **at or before** M15 confirmation only.
- Confirm at M15 `close_at`, execute earliest eligible M1 observed open **within 60 seconds**, single 1-oz position, single position at a time, deterministic stop-first if both intraminute stop and target hit, adverse opening-gap fill, $0.40 USD/oz **ALL-IN round-trip**. Do not add an additional spread or second commission. Year-end position close, yearly capital reset; do not stitch annual returns into a fictional continuous account.
- Frozen exploration years **2012 and 2013**, each exact private original `Gold data.zip` SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Both historically exposed design years, NOT independent out-of-sample.
- Execute 25,600 actual backtests for each year, planned **51,200 annual runs** if both finish, with full 12 exit-booked monthly net P/L per run, annual net after fee, number of trades, fees, worst month and M1 floating drawdown.
- Mandatory at least **six original-source canonical `run_fast` parity samples per year** (including monthly P/L, fees, filled count, total net, M1 floating max drawdown). Fail/withhold results if any sample mismatches.
- After both complete: exact parameter-ID join, count 24/24 positive months and annual-positive in both years, count >=16/24 and whether also annual-positive both. Do not optimize based solely on positive-month counts or retrospectively alter thresholds to make a winning claim.
- Run GitHub CI for full source and synthetic regression tests first; use exact CI-verified public source snapshot locally with the **private original quotes**. Never push source ZIP, raw BID/ASK quotes, or private full market bars to public GitHub.
- Stop/reject as monthly-consistency hypothesis if no 24/24 result; even 24/24 on exposed data is **not evidence of future monthly profits** and must face independent embargoed forward testing. No live trade recommendation.
