# BID/ASK Tick → M1 quote-parity gate — 2026-10-25

## Scope
Added `src/norisk_quant/quote_parity.py` and `tests/test_quote_parity.py`.
This is a **data-quality audit**, not a tick-fill engine and not evidence that
M1 candles contain true intraminute execution order.

`compare_bid_ask_ticks_to_m1(ticks, minutes, tolerance=1e-6)` requires:
- Observed tick events indexed by finite, sorted, timezone-aware **UTC** timestamps,
  with numeric positive BID and ASK, ASK >= BID.
- If event timestamps repeat, explicit numeric integral, unique, strictly
  increasing source `seq` per timestamp; never sort by price.
- M1 BID OHLC `o,h,l,c` and ASK OHLC `ao,ah,al,ac`, positive finite,
  plausible high/low, non-crossed BID/ASK, unique sorted UTC minute-open index.
- Finite nonnegative tolerance. No interpolation, forward fill or fabrication
  of missing tick minutes.

For each M1 bar the result includes `tick_present`, separate
`bid_max_abs_diff` and `ask_max_abs_diff`, mismatch flags for each side,
`both_quotes_match`, and `status`:
`MATCHED_OBSERVED_OHLC`, `QUOTE_MISMATCH` or `NO_TICKS`.
Missing ticks are **not** considered matches.
`summarize_bid_ask_parity` returns `PASSED_OBSERVED_OHLC_ONLY` only when
**every** supplied M1 bar has both quote sides matching within tolerance;
otherwise it returns `FAILED_OR_INCOMPLETE` and explicit coverage counts.

## Verification boundary
- 12 isolated local tests passed on Linux/Python 3.13/Pandas 2.2.3/NumPy 2.3.5
  before the source and test were pushed to the development branch.
- These tests cover exact matches, ASK-only divergence, missing/no-overlap
  minutes, crossed/nonfinite quotes, malformed tolerance, duplicate/unsorted
  timestamps and source sequence (including numeric-vs-lexical ordering).
- **Not** a full pytest run against the latest GitHub commit. **Not** a
  GitHub Actions success. Original licensed Gold data.zip and independent
  observed tick feed were not available for this verification.
- No historical strategy backtests were repeated. No raw data were committed.

## Research guardrails
This quote-parity gate is distinct from the primary synthetic-price research
execution model, which charges **one fixed ALL-IN $0.40 per ounce per completed
round trip** and adds no second spread/commission/slippage. The gate does not
alter P/L, strategy signals, or costs.

Even perfect BID/ASK OHLC agreement does **not** establish tick completeness,
provider authenticity, intra-minute path, order queue priority, or broker fill
parity. Any claim of MT5 broker parity requires an independent broker feed,
matching contract settings, and trade-by-trade replay evidence.

Draft PR #1 remains unmerged until the full current package suite, actual-data
parity and GitHub CI runner are independently verified.
