# FAC025-ENTRY-A — original Gold ZIP structural feasibility (2026-10-29)

**Scope:** The original private `Gold data.zip` was materialized locally and SHA256-verified as `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. This report publishes **aggregate counts only**, not BID/ASK M1 quotes. Source script: `scripts/research_fac025_source_feasibility.py`; regression tests: `tests/test_research_fac025_source_feasibility.py`.

**Status: SOURCE-ONLY STRUCTURAL FEASIBILITY — NOT A BACKTEST.** This is an independent, after-registration source coverage diagnostic of the already frozen FAC025-ENTRY-A sweep + two *older* H1 trend + 0.0004–0.0015 normalized stop envelope. It does **not** execute the frozen 72 filter settings (NY session/DST, realized-loss halt, volatility gates), authenticate quote receipt timestamps, authorize entries, model stop/target fills, enforce one-slot portfolio capacity, calculate returns, or establish clean OOS. No refit was made after observing the results.

| Year | Original M1 observed | Fully observed M15 | Two-prior-H1 contexts | Directional sweep candidates | Risk-envelope passes | Later M1 open observed* |
|---|---:|---:|---:|---:|---:|---:|
| 2012 | 352,975 | 23,197 | 19,883 | 1,812 | 1,620 | 1,603 |
| 2013 | 352,317 | 23,023 | 19,536 | 1,700 | 1,428 | 1,413 |
| 2014 | 351,794 | 23,243 | 20,129 | 1,841 | 1,667 | 1,645 |
| 2015 | 353,772 | 23,543 | 21,223 | 1,977 | 1,784 | 1,756 |
| 2016 | 354,246 | 23,584 | 21,429 | 2,002 | 1,766 | 1,740 |
| **Total** | **1,765,104** | **116,590** | **102,200** | **9,332** | **8,265** | **8,157** |

*This checks only the **presence** of the minute-open timestamp exactly 60 seconds after a conservative hypothetical decision at M15 end + 60 seconds. It is **not** an authenticated, eligible, executable quote or a filled trade. 108 candidate timestamps lack this observed later open. Source months: 60/60 have at least one *structural candidate*, minimum **88 in June 2013**, maximum **189 in September 2015**. These are **candidate counts, not profitable months**.

Method: refuse incorrect source SHA, unaligned/duplicate/unsorted minute opens, crossed paired BID/ASK OHLC, invalid prices. Construct M15 only when all 15 observed M1 minutes are contiguous. Require four preceding complete M15 bars and two complete H1 closes ending no later than the candidate M15 **start**. Do not fabricate missing minutes, infer session status from a gap, or use future H1 closes. Original source has no authenticated receipt timestamps, so a live-causal claim is impossible from this data alone.

**P/L and risk:** New original-source *strategy backtests* **0**; source-verified monthly net P/L **N/A**; worst losing month **N/A**; verified M1 floating drawdown **N/A**; fixed ALL-IN roundtrip fee **$0.40/oz unchanged**; independently approved strategies **0**. The 72 FAC025 settings remain **one correlated hypothesis**, not 72 independent trials. 2012–2016 remain historically exposed, not clean OOS.

**Next gates:** obtain authenticated paired BID/ASK receipt chronology or explicitly label any replay a non-authenticated historical proxy; run the frozen session/regime/loss gates, canonical-vs-fast parity and shared-capacity execution; report exits booked by month, fees, actual observed M1 floating equity, worst month, sample size and gaps. Maintain an embargoed prospective evaluation and multiple-testing controls. PR #1 stays Draft; no MT5 live, no billing changes, no raw quotes on GitHub.
