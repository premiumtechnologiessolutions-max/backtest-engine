# FAC025 — Original-source observed entry-open spread stress (2026-10-29)

Original private ZIP SHA256: 1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121. This is a source-only independent structural cross-check of the frozen FAC025-ENTRY-A M15 sweep/H1 trend candidates and the *observed next-open* BID/ASK spread. No receipts authenticated, fills, P/L, drawdown, portfolio backtest, or clean OOS. Years 2012–2016 are historically exposed. No private raw quotes published.

The independent module reconstructs 15-observation M15 and two completed prior H1 contexts; rejects invalid/crossed BID/ASK OHLC, duplicate/unsorted minutes; and observes entry BID/ASK open only at candidate M15 end +120s, after hypothetical decision at end +60s. No fabricated minutes. It cross-checks five yearly candidate counts against the existing original-source feasibility module. NY 08–12 and 09–13 are overlapping DST-aware subsets; never add them.

| Year | Risk candidates | Observed next opens | All-hours spread >$0.40 | NY 08–12 opens / >$0.40 | NY 09–13 opens / >$0.40 |
|---|---:|---:|---:|---:|---:|
| 2012 | 1,620 | 1,603 | 182 | 282 / 25 | 263 / 19 |
| 2013 | 1,428 | 1,413 | 192 | 226 / 23 | 206 / 24 |
| 2014 | 1,667 | 1,645 | 24 | 310 / 1 | 288 / 0 |
| 2015 | 1,784 | 1,756 | 35 | 221 / 0 | 224 / 1 |
| 2016 | 1,766 | 1,740 | 22 | 306 / 0 | 287 / 0 |
| **Total** | **8,265** | **8,157** | **455 (5.58%)** | **1,345 / 49 (3.64%)** | **1,268 / 44 (3.47%)** |

The 9,332 pre-risk candidates match the earlier feasibility report. July 2013 had 92/121 (76.03%) all-hours observed candidate entry opens with spread >$0.40; largest candidate entry spread was $1.56/oz. Floating-point comparison uses >0.40 + 1e-9. These are quote diagnostics, **not additional commission**. The fee remains exactly $0.40/oz ALL-IN roundtrip; no spread is added twice. A quote spread above $0.40 does not itself establish a realized transaction cost or a losing trade.

Reproduce locally: python -m scripts.research_fac025_entry_spread_stress /private/Gold-data.zip. Keep full monthly aggregate output local and never upload original ZIP, individual timestamps or raw BID/ASK. Code: scripts/research_fac025_entry_spread_stress.py; tests: tests/test_research_fac025_entry_spread_stress.py (11 synthetic cases locally passed). SHA256 is checked before reading source years. No frozen strategy parameters retuned. Original-source strategy backtests added: **0**; monthly net, worst month, observed M1 floating DD: **N/A**; approved strategies: **0**.

Still required: independently authenticated pre-signal receipts, actual one-slot canonical BID/ASK portfolio execution and fast/reference equity parity, prospective embargoed OOS and multiple-testing controls. Keep PR Draft, no live trading.
