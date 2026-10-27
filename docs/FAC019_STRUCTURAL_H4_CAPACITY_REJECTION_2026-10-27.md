# FAC019 — pre-execution structural impossibility audit (2026-10-27)

**Result: STRUCTURALLY UNREACHABLE under the frozen rules.** Frozen before any outcomes at commit `530fc65c24d16b1733543f7bf7eceafb5b411542`. Do not relax the 8-H4-bar requirement after inspecting this result. The 16,384 correlated parameter specifications per year were **NOT** executed as M1 backtests.

Private local original `Gold data.zip` SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` was verified. Independently reconstructed complete UTC H4 candles from the actual observed M1 bars (240 consecutive M1 timestamps per candle, no filling). Counts:

| Original source year | Complete H4 candles | Maximum consecutive complete H4 candles | Eight-consecutive-H4 windows |
|---|---:|---:|---:|
| 2012 | 1,213 | **5** | **0** |
| 2013 | 1,197 | **5** | **0** |

FAC019's frozen causal H4 filter requires **eight consecutive complete H4 bars**. With a maximum of five in either year, every parameter ID must have zero valid H4 context, independent of London/NY signal thresholds, SL/TP, or P/L. This is a proof of **necessary-condition infeasibility**, not a failed profit optimization. The separate local signal-only prototype indeed counted zero eligible signal groups; official checked-out GitHub runner/source parity has NOT been executed and is not claimed. Do not run the 32,768 planned annual M1 replays.

Added `scripts/audit_fac019_h4_feasibility.py` and synthetic tests for complete-window counts, market gaps, malformed time indexes, and no fabricated bars. **11/11 isolated synthetic cases passed locally**; GitHub CI for the final repository head must be checked separately. The audit is deterministic and reports aggregate counts only. The existing `norisk_quant.strategy.aggregate_bars` will be used when executing the official checkout; this report's observed counts came from a separate local complete-bar reconstruction, not an official-source replay.

**Accounting impact:** 0 new annual M1 backtests; 0 new monthly P/L; 0 new fills or parity samples; no new risk or profitability figures. Factory totals remain **590,380 active annual replays and 7,084,560 active monthly values**. Historical 2012–2016 are exposed, not clean OOS. Existing FAC007/FAC016/FAC017/FAC018 remain rejected. Do not change the fixed $0.40/oz all-in fee, public repository visibility, privacy/billing, or trade live. Keep PR #1 Draft/unmerged.

**Next family design rule:** Any new H4 lookback must be checked against actual contiguous H4 market coverage **before freezing a large grid**. A logically different family can use a bounded age-aware sequence of completed H4 observations that explicitly treats daily closures as boundaries, but it must be separately preregistered and never called a repair/retest of FAC019.
