# FAC025-ENTRY-A — original-source NY-session structural subset (2026-10-29)

**Status: source-only prefilter diagnostic, NOT a backtest, fill, verified order, or P/L claim.** This adds a descriptive New York-local session subset to the *already frozen* FAC025-ENTRY-A structural audit; it does not change entry logic, filter thresholds, risk sizing, $0.40/oz ALL-IN fee, or the 72 correlated parameter specifications (one hypothesis).

Source: private `Gold data.zip`, SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`, checked locally. Public repository contains **only aggregate counts**. Code: `scripts/research_fac025_source_feasibility.py`; synthetic regression: `tests/test_research_fac025_source_feasibility.py`. This audit checks the NY clock on the **hypothetical** decision at the completed M15 end + 60 seconds and only includes structural risk-envelope candidates with the required subsequent observed M1 open at M15 end + 120 seconds. A timestamp being present is NOT proof of an eligible or executable quote. Session mapping uses `America/New_York` with historical DST.

| Year | Risk-envelope passes (all hours) | Subsequent M1 open observed (all hours) | NY 08–12 candidates | NY 09–13 candidates |
|---|---:|---:|---:|---:|
| 2012 | 1,620 | 1,603 | 282 | 263 |
| 2013 | 1,428 | 1,413 | 226 | 206 |
| 2014 | 1,667 | 1,645 | 310 | 288 |
| 2015 | 1,784 | 1,756 | 221 | 224 |
| 2016 | 1,766 | 1,740 | 306 | 287 |
| **Total** | **8,265** | **8,157** | **1,345** | **1,268** |

The 08–12 subset is **16.49%** of all 8,157 observed-open structural candidates (690 bullish, 655 bearish); 09–13 is **15.54%** (679 bullish, 589 bearish). **Do not add the session columns**: 09–12 overlaps. Each session had at least one such candidate in **60/60 historically exposed months**; this is NOT 60 profitable months. Minimum monthly candidate count: 08–12 **8 (May 2013)**, 09–13 **9 (September 2013)**. These counts are not 72 independent trials, and not the completed frozen volatility/loss gates.

**Explicit missing gates:** historical source has no independently authenticated M1 receipt/confirmation chronology; the 72 frozen volatility settings and causal realized-loss halts were **not** applied; no stop/target execution, one-slot capacity allocation, BID/ASK exit fill, canonical/fast P/L parity, floating M1 equity, or forward OOS evaluation was performed. Session counts are **potential candidate ceilings before other filters**, not trade-count guarantees. Month-by-month profitability and worst-month loss remain **N/A**; observed M1 floating drawdown **N/A**; new original-source strategy backtests **0**; approved strategies **0**.

This audit is descriptive on exposed 2012–2016 history; do not refit or select the session from its counts. The next step is a fully frozen, one-slot, source-audited BID/ASK historical-proxy replay, with exact monthly net, fee, worst month, observed floating drawdown, missing-minute integrity, and prospective embargoed validation. PR #1 remains Draft and unmerged. No raw quotes or live MT5 execution.
