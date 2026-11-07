# FAC019 — PRE-OUTCOME FROZEN London→New York cross-session range transfer (2026-10-27)

**Status at freeze: ZERO executions, ZERO inspected signal counts or P/L.** One distinct hypothesis family; 16,384 **correlated parameter specifications per year**, NOT 16,384 independent hypotheses. Historical design years 2012 and 2013 are exposed, NOT clean OOS. Do not relabel any historical year independent.

## Distinct economic hypothesis

An unusually wide or narrow **completed London morning range** can alter the probability of the first New York morning breakout either continuing or failing. This is a cross-session information-transfer experiment, not FAC018's time-weighted inventory anchor, FAC017's two-bar shock, FAC016's H1/H4 Fibonacci, FAC014's prior-day reclaim, or a generic moving-average crossover. All signals are causal, gap-aware and evaluated at the close of a complete M15 bar. London local time is Europe/London 08:00–12:00; NY local time is America/New_York 09:30–13:30. Use IANA timezone conversion per historical date, never a fixed UTC offset.

**Input gate:** Use only original local private `Gold data.zip`, SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Each session must have all 16 observed, unique, aligned, complete M15 bars. No imputation; reject days with incomplete London or NY event windows. London H/L are computed from its 16 bars and are available only after its final close; reject any NY event whose timestamp is not strictly later. Prior N London sessions must each be complete; they need not be consecutive calendar dates because weekends/holidays exist, but require the most recent one within 7 calendar days and the oldest within 60 calendar days. Reject missing sessions rather than filling them. Baseline B is the median of the **previous N complete London session high-low ranges**, excluding today's London session; B must be finite and positive. Today's completed London range L/B must be >= q and <=3.0 (upper bound is a pre-known shock halt).

**NY event:** At NY M15 bar j-1 close, price first crosses beyond today's completed London high + b*B (upper) or low - b*B (lower); the preceding NY M15 j-2 close was not beyond that same boundary. j-1 and j must be consecutive observed completed M15 bars within NY local session; j close must be strictly before NY session end. For FOLLOW, j closes outside the same boundary in the breakout direction and has a same-direction candle body. For FADE, j closes back inside the original London range and has an opposite-direction candle body. Generate at most **one first qualifying signal per NY local date per parameter rule**; no event after an earlier qualifying signal. Risk unit R = median of the preceding 20 **contiguous, complete M15 ranges** ending j-1, excluding j, strictly positive. Signal timestamp is j close, not j open.

**Completed H4 regime:** At signal close use the latest fully closed H4 bar with age <=4h and 8 contiguous complete H4 bars. Its range / median range of the 7 preceding completed H4 bars must be finite, positive and <=2.5 (pre-known halt); CALM if ratio <=1, ACTIVE if >1. All unavailable, stale or noncontiguous context halts entry. No same-bar or future H4 input.

## Frozen Cartesian grid and capacity preflight

- Prior complete London sessions N = [10, 15, 20, 30].
- London range / prior median minimum q = [0.75, 1.00, 1.25, 1.50].
- First-break buffer b in units of prior London median B = [0.00, 0.10, 0.20, 0.30].
- NY reaction mode = [FOLLOW, FADE].
- H4 regime = [CALM, ACTIVE].
- Stop and target multipliers independently = [0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.25] * R.
- **4×4×4×2×2×8×8 = 16,384 correlated specs per year, 32,768 planned annual replays, 256 unique signal-rule groups before exit-parameter duplication.** Same ID and same rules across 2012/2013.

**Before any SL/TP M1 backtest**, count only causally confirmed signal timestamps for all 256 groups in each year, no P/L or winner selection. With at most one fill per signal and frozen minimum >=100 fills **in EACH year**, discard a group if either year's signal count <100; count same group ID jointly across years. If no group qualifies, declare `STRUCTURALLY_UNREACHABLE` and execute **zero** annual backtests; do not change the threshold, group definitions, or optimize from the counts. Preflight is necessary, not sufficient for trading profitability.

## Execution, validation, acceptance

For any group passing signal-only preflight: one ounce, exactly $0.40/oz ALL-IN roundtrip, one open position per strategy, next eligible observed M1 open within <=60 seconds of signal close or expire, stop-first if both touched, adverse gap-through, no fabricated minutes or lookahead. No M1 raw data in GitHub. Report each UTC exit-booked month including zeros, gross/net, fees, trade counts, expiries, worst month, annual net, observed M1 floating DD, coverage, signal-stream hashes, and duplicates. Full canonical run_fast parity on precommitted samples and independent reference slow parity; actual one-position **shared-capacity** portfolio test separately before any portfolio claim. Never sum standalone profits.

Frozen joint gate: >=100 fills EACH year, >=18/24 strictly positive months, positive net EACH year, worst month >=-$20/oz, max annual observed M1 floating DD <=$100/oz. Passing the exposed historical gate is exploratory, never clean OOS. For prospective evaluation, lock one model/portfolio **before** newly arriving data, embargo overlapping signals/trades, track family-wise multiple testing and data-snooping, and do not promise 12/12 or live profits.

**At freeze:** 0 FAC019 original-data backtests, 0 FAC019 observed monthly P/L, 0 canonical parity checks. Do not modify rejected FAC007/FAC016/FAC017/FAC018 to force success. PR #1 stays Draft/unmerged; no broker trading, billing, privacy or repository-visibility changes.
