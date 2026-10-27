# Mixed raw JSON boolean-coercion gate — 2026-10-27

**Scope:** Input-integrity fix only; no strategy, execution, fixed fee, or performance change.

## Reproducible failure mode

Pandas `pd.to_numeric(pd.Series([True, 1.0], dtype=object))` yields
`[1.0, 1.0]`. The existing source-normalization check rejected entirely
boolean quote *columns* after conversion, but not **mixed** JSON/Python
boolean cells embedded among valid numeric values. A boolean price could
therefore be converted to a plausible price and pass OHLC integrity checks.
The same issue applied to a mixed timestamp column (e.g. `False` -> 0).

## Change and tests

`normalize()` now checks every raw timestamp and all eight BID/ASK fields
for native `bool` or NumPy `bool_` **before** calling `pd.to_numeric`.
The common numeric dtype path remains fast; object-typed source columns are
scanned for boolean cells. Genuine numeric-looking text remains supported
through the original conversion path.

Synthetic regressions cover 9 fields x 3 boolean variants x both strict and
non-strict normalization, direct JSON ingestion, ZIP import refusal without
Parquet output, and a valid numeric-string control. A zero-spread $1.00
synthetic quote is deliberately used to demonstrate that a coerced `True`
would otherwise pass all price geometry checks.

## Certification boundary

The original Gold data.zip SHA256 contract remains
`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
The archive and independent 13-field reference ledger were **not available**
for this change; no original-source replay or OOS validation was performed.
Confirm GitHub Actions on the **exact resulting commit** before claiming
full-suite success. No raw private market data was uploaded. PR #1 remains
Draft and unmerged. Repository visibility must be treated as **public**
until a verified privacy change, regardless of project naming.
