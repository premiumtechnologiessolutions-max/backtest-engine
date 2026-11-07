# Tick/M1 parity summary fail-closed integrity — 2026-10-27

The quote parity summary previously counted `both_quotes_match` without verifying
the other report fields. A corrupted or edited DataFrame could therefore claim
`PASSED_OBSERVED_OHLC_ONLY` despite `tick_present=False`, a contradictory
mismatch flag, a forged status, or missing/invalid difference measurements.

The summary now requires the full comparison schema; nonnull boolean flags;
a consistent tick-present / mismatch / both-match relationship; the exact
three-valued status mapping; and finite nonnegative differences for observed
tick minutes (NaN for absent tick minutes). It rejects contradictory input
rather than producing a misleading PASS. Twelve synthetic regressions cover
corruptions and valid matched/missing/mismatched reports.

This does **not** independently authenticate the tick source, establish
intraminute completeness, verify the chosen tolerance, or validate broker
fills. No strategy, execution fee, market dataset, or trading outcome changes.
The authorized original Gold ZIP 13-field replay remains outstanding.
