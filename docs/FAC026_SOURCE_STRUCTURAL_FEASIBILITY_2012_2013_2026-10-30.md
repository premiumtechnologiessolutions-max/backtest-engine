# FAC026 — original private-source M1 structural feasibility audit (2026-10-30)

**Status: SOURCE-SHA-VERIFIED STRUCTURAL SCREEN ONLY; NOT A BACKTEST, NOT AN EXECUTABLE FILL, NOT OOS.** No original quote data is committed.

## Frozen hypothesis and scope

The hypothesis and 32 correlated configurations were frozen **before** opening the source results in [FAC026 preregistration](FAC026_FROZEN_COMPRESSION_BREAKOUT_H1_2026-10-30.md). This run screens 16 distinct structural combinations (N=8/12, compression=.65/.80, H1 efficiency=.35/.55, NY session=08–12/09–13); the other factor, daily closed-loss halt=$2/$4, **cannot be evaluated without a chronological executed trade ledger**. Thus 32 frozen settings are NOT 32 independent hypotheses, and this is NOT 32 completed portfolio backtests.

Original local `Gold data.zip` SHA256: `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. The reproducible, offline scanner is `scripts/research_fac026_original_source_structural.py`; synthetic tests are `tests/test_research_fac026_original_source_structural.py`. It checks paired BID/ASK quote ordering, UTC minute alignment, strict observed 15/60-minute completeness, H1 strictly completed by M15 trigger close, M15 compression and breakout, DST-aware NY session, and normalized trigger-risk <=0.002. The next-open availability check requires an actual observed opening minute **strictly later** than the one-minute-delayed decision and within 60 seconds of that decision. It does not fill a trade.

## Local original-source observations (2012–2013; historically exposed)

| Metric | 2012 | 2013 | Both |
| --- | ---: | ---: | ---: |
| Original observed M1 minutes | 352,975 | 352,317 | 705,292 |
| Unique structural trigger timestamps across all 16 variants | 12 | 6 | 18 |
| Unique triggers with observed eligible next M1 open | 12 | 6 | 18 |
| Calendar months with at least one structural trigger in **any** variant | 7/12 | 4/12 | 11/24 |
| Calendar months without **any** structural trigger | 5/12 | 8/12 | 13/24 |
| Largest number of triggers in any one structural variant | 6 | 4 | max 9 for a single same-variant 2-year pair |
| Aggregate counts across correlated variants (**not unique trades**) | 24 | 11 | 35 |

The **upper bound** of only 18 distinct candidate decision timestamps over 24 exposed months and 13 months without any candidate makes FAC026 **infeasible as a standalone strictly-positive-every-month strategy** under the frozen structural filter and one-slot, flat-when-idle interpretation. The closed-loss halt and shared-capacity competition can only remove these candidate opportunities. This is a *structural sample-size feasibility finding*, not a P/L or return result. Different strategies could in principle cover missing months, but no such portfolio is validated.

**New executed strategy backtests: 0.** Monthly realized net P/L: **N/A**. Worst realized month: **N/A**. Monthly/global observed M1 floating drawdown: **N/A**. Fees: **not incurred or simulated**; any future roundtrip must use exactly **$0.40/oz ALL-IN**. Approved strategies: **0**. No broker tick fill verification, no canonical run/run_fast parity for this family, no untouched prospective OOS.

## Reproduction and limits

```bash
python scripts/research_fac026_original_source_structural.py '/private/path/Gold data.zip' --out /private/path/fac026_structural.json
python -m pytest -q tests/test_research_fac026_original_source_structural.py
```

Keep the ZIP and the detailed local output outside the public repository. This is a **source-observed structural diagnostic**, not an order, execution receipt, portfolio P/L, or production-grade proof. The scanner's output is aggregate counts and month counts only, with no quote rows. Local diagnostic JSON SHA256 (sorted, indented): `02f0686787d91845fa09897051e5a108f8a426688c6660e2b54d3b5ad26603a2`. A future independent cross-check against the frozen `evaluate` function is required before treating these counts as canonical signal parity. The prior FAC025 and FAC007 rejections remain unchanged. Keep PR #1 Draft, do not merge, do not publish private quotes or connect MT5.
