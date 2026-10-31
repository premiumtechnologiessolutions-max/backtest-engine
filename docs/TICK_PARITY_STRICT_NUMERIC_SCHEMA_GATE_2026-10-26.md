# BID/ASK tick-to-M1 parity: strict numeric schema gate — 2026-10-26

## Failure mode

The observed-tick BID/ASK comparison used `to_numpy(dtype=float)` for both raw tick quotes and reference M1 bars. That operation can silently turn boolean `True` into `1.0` and numeric-looking text into floats. An otherwise matching dataset could be reported as `PASSED_OBSERVED_OHLC_ONLY` even though its quote columns had malformed source dtypes. This was a **data validation** issue, not evidence of a real-market strategy profit or broker-fill discrepancy.

## Correction

`compare_bid_ask_ticks_to_m1` now requires genuine numeric, non-boolean Pandas dtypes for **both tick quote columns** (`bid`, `ask`) and **all eight M1 BID/ASK OHLC columns** (`o,h,l,c,ao,ah,al,ac`) before conversion or resampling. Integers and floats remain accepted. A boolean or numeric-looking text column fails closed with an explicit error.

`tests/test_quote_parity.py` adds **20 negative cases** (2 malformed types × 10 quote columns) and **one positive mixed-integer/float case**. The existing source-sequence handling remains unchanged; CSV event-sequence text is a distinct concern from quote schema integrity.

## Verification boundary

The change and regression specifications are committed to `feat/quant-engine-foundation`. **Do not infer a passing full test suite merely from committed tests.** Verify GitHub Actions against the precise HEAD SHA and report the actual result. No original Gold ZIP, independent broker ticks, or archived 13-field trade ledger were accessible in this execution environment; original-data replay and tick-feed completeness remain unverified.

The comparison remains a quote-OHLC integrity audit, **not** a tick execution model, provider authentication, broker fill guarantee, or proof of profitable trading. Research execution costs remain exactly **USD 0.40 per ounce ALL-IN per round trip**. No raw market quotes uploaded, no changes to strategy logic or live execution, and PR #1 remains Draft.
