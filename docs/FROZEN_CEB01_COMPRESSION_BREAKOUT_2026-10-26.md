# Frozen hypothesis CEB-01 — Compression-to-breakout (2026-10-26)

## Status before examining any historical result
**DEFINED AND CODE-COMMITTED, UNVALIDATED.** Codes `src/norisk_quant/compression_breakout.py` and `tests/test_compression_breakout.py`. Commit `2bfd0cb3a17b1baa632ad42d5ba453aa5374041c` was created before opening any CEB historical backtest results.

## Distinct hypothesis
An XAUUSD market that closes outside a narrow 8-bar M15 or H1 range after volatility compression may exhibit short continuation, unlike the previously rejected quote-gap fade and liquidity sweep/reclaim. This is an empirical question, not an investment belief.

Frozen rules: 8 *complete* prior M15/H1 bars, prior range width <= 0.60 times rolling median of the 48 preceding 8-bar ranges; current candle opens inside the prior range, closes beyond prior high/low by >= $0.25. Reject windows crossing a missing aggregated bar. Signal timestamp = current full candle close, entry at earliest available M1 open, no lookahead. Protective distance from signal close to opposite prior range boundary plus $0.10; accept only $0.75-$20.00; target 1.8x initial stop distance. No trailing or discretionary modifications.

## Predeclared experiment matrix and stop rule
- **CEB-M15**: all parameters exactly as above, timeframe M15.
- **CEB-H1**: all parameters identical except H1.
- First examine **2012 and 2013 individually**, two runs per year. Each year is a separate self-contained simulation; never call their sum a continuous account equity series. All four outcomes are informative but part of the exploratory/historically exposed sample, **NOT independent holdout**.
- Cost **$0.40/oz ALL-IN round-trip**; single 1-oz synthetic BID-reference Market position, stop-first intrabar, no favorable assumed gap stops, stale signals skipped; record weekly and monthly settled and marked equity, max drawdown, trades and fees.
- **Pass-to-next-design-stage threshold specified in advance**: across both 2012 and 2013, a timeframe qualifies for additional scrutiny only if it has **at least 16/24 positive months**, > 0 net P/L after fees, and >= 50 executed trades in each calendar year. Otherwise classify **REJECT**; do not tune parameters to rescue it. If one qualifies, freeze it without alteration before looking at other years. This is a research prioritization rule, not evidence of true OOS.
- Stage 2 would be 2014–2016 *unchanged*; historic data already previously inspected for many unrelated ideas, so label exposed corroboration only.
- No data inspection or optimization after seeing monthly outcomes; future independent prospective period required for a credible monthly-stability claim.
- Reference/fast execution trade parity is a separate engine-implementation check. It cannot establish real broker fills or strategy profitability.

## Constraints
Input source `Gold data.zip` must SHA-256 match `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Never upload quote data to public GitHub or Actions, never alter billing/PR draft/merge, and never layer spread/slippage or another commission over the fixed $0.40/oz fee.
