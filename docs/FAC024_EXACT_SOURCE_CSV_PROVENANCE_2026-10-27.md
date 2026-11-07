# FAC024 exact-source CSV adapter — 2026-10-27

**Status: opt-in provenance hardening, synthetic tests only. No prospective market month is complete.**

## Problem

The generic `register_closed_month(month, path, observed_minutes, ...)` takes a file path **and a separately supplied DataFrame**. It hashes the file, but cannot establish that the DataFrame was parsed from those bytes. Accidentally passing a different, truncated or modified DataFrame would create a misleading source record.

## Implemented

`src/norisk_quant/prospective_csv.py` adds `register_closed_month_csv` for a **specific, documented** M1 source format. It reads the original local bytes into one immutable buffer, parses the observations **from those bytes only**, calls the existing closed-month and quote-geometry validator, then requires the source file's registered SHA256 and byte length to equal the exact parsed buffer. A file changed between parsing and registration is rejected.

Accepted CSV format:
- UTF-8, first line exactly `at,o,h,l,c,ao,ah,al,ac` (no additional/duplicate columns).
- UTC minute-open timestamps exactly `YYYY-MM-DDTHH:MM:00Z`, no ambiguous offsets or naive times.
- Plain decimal numeric BID/ASK OHLC fields, no scientific notation, NaN, infinity, or missing fields.
- The existing common validator enforces positive finite prices, both OHLC envelopes, non-crossed BID/ASK, strictly increasing unique UTC minutes and frozen month bounds.
- The existing registration contract enforces registration after the month has ended and chronological manifest append.

This is **optional**: generic broker Parquet/JSON exports are not claimed to conform. This adapter is deliberately strict, not a universal file parser.

## Evidence and limitations

`tests/test_prospective_csv.py` covers the valid synthetic registration and chain, malformed headers, timestamps, numeric values, duplicate timestamps, crossed quotes, malformed candles, invalid month, non-UTF8 bytes, and a simulated post-parse fingerprint mismatch. These tests do **not** exercise real XAUUSD source files, broker fills or monthly strategy P/L.

The adapter binds a parsed DataFrame to local source bytes but does **not** prove the broker's authenticity, completeness of all trading sessions, a trusted registration clock, external immutability, or truly unseen observations. **Two minutes in a CSV can still be registered as two observed minutes, not certified as a full trading month.** A separate coverage/calendar/provenance acceptance gate is required before FAC024 may be evaluated as twelve full months. The `all_months_registered` predicate checks the chronological manifest chain, not market-calendar completeness.

FAC024's signal parameters, fixed $0.40/oz research fee, frozen 2026-11 to 2027-10 window, and historical results are unchanged. No source data, paths or private trade ledgers were committed. PR #1 remains Draft; the repository is currently public.
