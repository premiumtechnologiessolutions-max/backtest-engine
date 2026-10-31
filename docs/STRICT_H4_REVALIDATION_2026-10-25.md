# Strict H4 bar completion audit — October 25, 2026

## Decision

**Do not trust or promote the old H4 MACD/RSI/Stochastic monthly-profit statistics as finalized.** Legacy scripts accepted H4 candles with as few as 170 of the 240 required M1 candles. New strict replay recomputed H4 candles, indicator histories, signal timings, and exits with only 240-of-240 minute candles. This is a policy sensitivity study (and an intentionally conservative full-candle convention), NOT proof that 15.6% of the original M1 source prices were corrupt.

**Source:** private `Gold data.zip`; SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` (raw source not committed).

**2011–Sept 2026 warmup + replay**: 5,570,657 M1 candles; old H4 method accepted **23,230** bars, of which **3,613 (15.553%) were incomplete**, strict retained **19,617** fully observed H4 candles. Legacy threshold was 170 M1 points; strict enforces complete 240-minute time buckets with first+last minute present.

### Frozen configuration results (USD per 1 oz, ALL-IN fixed $0.40 per roundtrip)

| H4 model | Candle rule | Design 2012–19 profitable months /96 | Design net | Exposed 2020–Sep26 profitable months /81 | Exposed net |
|---|---|---:|---:|---:|---:|
| T04 MACD12/26/9, zero filter, RR2, original | Legacy 170/240 | 55 | +$523.10 | 44 | +$806.53 |
| T04 MACD12/26/9, zero filter, RR2, original | Strict 240/240 | **46** | **+$398.84** | **39** | **+$453.51** |
| M01 RSI7 OS25 OB80 H4 inverse | Legacy | 36 | +$37.88 | 26 | -$193.03 |
| M01 RSI7 OS25 OB80 H4 inverse | Strict | **28** | **+$55.70** | **27** | **-$26.93** |
| M02 Stoch14 zone20 H4 original | Legacy | 38 | -$345.39 | 37 | +$31.76 |
| M02 Stoch14 zone20 H4 original | Strict | **47** | **-$62.73** | **38** | **+$309.74** |

These values resulted from complete replay and indicator regeneration with **no retuning**. The same cost and M1 conservative stop-first/gap-carry rules remained fixed. **None won every month**. September 2026 is partial, and 2020–26 was repeatedly exposed in earlier research; it is NOT independent out-of-sample.

### Reproducibility gates met locally

Before applying the change, standalone legacy code was rerun on the raw ZIP and compared row by row with the previously archived output, with **exact timestamp AND $P/L equality**:
- MACD: 422/422 trades matched, max P/L difference $0.
- RSI: 278/278 matched, max difference $0.
- Stoch: 1,215/1,215 matched, max difference $0.

Monthly ledgers were recomputed and checked against every replay's trade and period count. Details and scripts saved to the user's conversation as `NoRiskFX_Strict_H4_Candle_Revalidation_2012_2026_2026-10-25.zip`; includes annual bar quality, monthly 2012–2026, pre-2020 split metrics, individual before/after trade ledgers, source code, SHA, and parity JSON. Source ZIP intentionally excluded from the checkpoint.

### Central engine update

`src/norisk_quant/strategy.py` rejects misaligned M1 timestamps and requires all timeframe minutes; `tests/test_strict_higher_timeframe.py` explicitly asserts 170/240 H4 and 45/60 H1 are **NOT** complete candles, as well as time alignment, source duplicate protection, and first-minute missing scenarios.

**Not yet proven:** Central GitHub CI execution is blocked by exhausted private-repo GitHub Actions quota through Oct 2026, Issue #2. Results above use a local reproducing research replay, not trade-by-trade parity with Github's engine. FVG H1/H4 inherited earlier partial-candle assumptions and must be reaudited before combination with newly corrected MACD.

**Next:** freeze the same full-candle policy for all legacy source variants, retest only impacted candidates, compare full trade ledgers with central engine after runners pass; research a genuinely different strategy under pre-2020 design gates. Never retune based on exposed 2020–26 monthly performance and claim independent OOS or guaranteed monthly income.
