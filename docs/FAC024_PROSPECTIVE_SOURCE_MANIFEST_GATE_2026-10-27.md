# FAC024 prospective source-manifest gate — 2026-10-27

**Status: code and synthetic tests only; 0 prospective months, 0 real-source FAC024 replays, no independent OOS acceptance.**

FAC024 was frozen earlier on commit `46c4fbf59c4c052fca4404b9b93588b11daac561` with exactly one M15 sweep/spread-recovery hypothesis. This change does **not** change entry logic, parameters, stop/target, the $0.40/oz all-in simulation cost, or its 2026-11-01 through 2027-10-31 UTC prospective window. No outcomes have been inspected for FAC024.

## New fail-closed controls

`src/norisk_quant/prospective_manifest.py` provides:
- Exact twelve-month calendar whitelist (2026-11 through 2027-10), no historically exposed 2010–2026 substitute.
- UTC-aware source registration only **after** each calendar month has ended, with explicit as-of time, and strictly increasing one-time chronological month registration.
- SHA256 of the original **local partition bytes** (streaming, no market data upload), byte length, observed M1 count, first/last observed UTC opens.
- Validation of unique sorted minute-aligned M1 timestamps, unique quote-column names, real finite positive non-boolean/non-complex BID/ASK OHLC, valid BID and ASK high/low envelopes, and no crossed quotes; missing minutes are not filled or silently counted as observed.
- SHA256 chained record digests, tamper detection, and file rehash before any evaluation. A partial manifest cannot pass the twelve-month completeness gate.

**Critical provenance limitation:** the caller must independently prove that the supplied M1 DataFrame was parsed from the exact fingerprinted file. This module cannot certify that relationship by itself, or validate tick execution, holidays, margin, fees beyond the frozen model, the broker's price source, or whether a source was truly unknown to researchers. A user-controlled registration timestamp and a chain inside a mutable Git repository are **not** an external trusted timestamp or an immutable audit log. For research acceptance, publish the metadata digest to an independent timestamped archive and preserve private original files in access-controlled storage. Do not commit raw quotes, source file paths, trade ledgers, or private datasets to this public repository.

## Acceptance remains blocked

- At 2026-10-27, the prospective start date is in the future. No qualifying future source month is complete.
- No monthly net P/L, worst-month P/L, fees, full floating M1 drawdown, trade sample size, or reference/fast parity was measured for FAC024.
- Future acceptance requires exactly twelve complete UTC months, source-to-parsed-data provenance, reference/fast parity, one-position shared-capacity execution, preregistered risk/return gates, and multiple-testing controls. A 12/12 goal is not a guarantee.
- Existing exposed historical factory totals remain unchanged. No backtests were run in this change.

Synthetic tests: `tests/test_prospective_manifest.py`. Keep PR #1 **Draft and unmerged**. No billing, privacy, or live trading changes.

## Additional prospective quote-schema hardening (2026-10-27)

The registration validator now rejects impossible BID or ASK OHLC bars (high below open/close or low above open/close), duplicate column names, and complex-valued quotes before hashing the prospective metadata. Synthetic regression tests cover these malformed inputs. This changes **source acceptance only**; it does not alter FAC024's frozen trading rules, research window, execution fees, or previously reported historical outcomes. Full repository CI and actual prospective-data evaluation must be reported separately; no future calendar month is complete yet.
