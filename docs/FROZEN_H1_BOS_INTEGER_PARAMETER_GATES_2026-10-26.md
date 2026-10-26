# Frozen H1/BOS parameter integrity — 2026-10-26

## Scope and impact

The opt-in H1 freshness filter formerly checked only `max_regime_age_minutes < 0`. A NaN value compares false against both negative and positive bounds, so the later `elapsed > NaN` condition would also be false. This could silently disable the intended stale-regime cutoff. Infinity had a similar effect. Boolean, fractional, and string-like inputs were not strictly rejected for H1 bar counts or BOS discrete parameters.

The frozen BOS settings similarly accepted NaN/Infinity for `max_bos_waves_per_regime`, defeating the declared maximum-wave constraint. Noninteger pivot counts and expiries could fail later or produce misleading configuration records; a truthy string for `ignore_ambiguous_dual_pivots` could enable the flag despite its text being `"False"`.

## Changes

- `H1RegimeSettings`: enforce integer EMA span >= 2, integer slope lag >= 1, and nonnegative integer or None maximum regime age. Reject booleans, floats including integer-valued floats, NaN, Infinity, and strings. Accept Python and NumPy integral scalars.
- `BosFibSettings`: enforce positive integer pivot widths, order expiry minutes, and maximum BOS waves. Require a real Python boolean for `ignore_ambiguous_dual_pivots`.
- Convert accepted H1 age to Python `int` before multiplying by nanoseconds per minute, preventing `np.int64` overflow for very large (though unrealistic) user-supplied limits.
- Add `tests/test_h1_bos_parameter_type_contract.py` and a large NumPy age regression in `tests/test_h1_regime_age_gate.py`.

## Verification status

- **55/55 isolated local parameter-validation checks passed**, using locally reconstructed class definitions that match the changed validators; **not** a run of the actual GitHub checkout.
- **1/1 isolated local H1 filter test passed** using a reconstructed H1 module and synthetic 3,900-row M1 fixture, including stale 120-minute rejection and large NumPy integer age overflow protection.
- New regression tests are committed to GitHub, but **the full current-head repository pytest suite, installed-package test, and CI have not been executed successfully in this environment**. The original market ZIP and archived independent trade ledger were unavailable for fresh 13-field replay parity.
- These checks do **not** prove trading profitability, broker tick fills, or out-of-sample validity.

## Preserved contracts

Default `H1RegimeSettings(max_regime_age_minutes=None)` remains unchanged. The opt-in 120-minute filter and opt-in ambiguous dual-pivot exclusion retain their previous behavior for valid inputs. No trading rule, source data, fee model, or historical research result was altered. Canonical all-in fee remains exactly **$0.40 per ounce per completed trade**.

PR must remain Draft until current-head full-suite pytest, exact historical 13-field replay, and CI verification succeed. Do not commit raw gold archives or trigger Actions while quota is exhausted.
