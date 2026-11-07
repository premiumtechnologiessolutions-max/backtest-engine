# Source-archive stability gate for historical replay — 2026-10-29

## Scope

Two existing private-data entry points are affected:

- `scripts/run_bos_fib_frozen_sensitivity.py`: the frozen BOS/Fib H1 annual sensitivity study.
- `scripts/verify_bos_h1_parity.py`: independent 13-field historical trade-ledger parity.

Both already required the authorized original `Gold data.zip` with SHA-256
`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
They previously checked that digest **before** replay only. A source replaced
while an annual loader was running could be attributed to the earlier digest.

## New fail-closed behavior

Each entry point now hashes the source ZIP **again after all requested years
have been processed**. If the final digest differs, the run raises an error
rather than returning a successful combined replay or parity certificate.
The frozen annual runner performs the final check before writing
`frozen_sensitivity_summary.json`. Intermediate per-year diagnostic files
may already exist if this late check fails; **they must not be treated as
certified evidence without the combined summary**.

The new `tests/test_historical_replay_source_stability.py` uses synthetic
market fixtures and a deliberately mocked SHA response to test unchanged and
mutated source outcomes. No original market data or private reference ledger
was committed. This is not a new XAUUSD profitability result.

## Important limitations

This is a **persistent-change detection gate**, not an immutable filesystem
snapshot or protection against a deliberate change-then-restore race. The
independent archived reference files remain separate evidence and require
their own provenance controls. Existing calendar-month presence checks do not
prove full broker-session completeness, tick-order fidelity, or live fill
quality. No 2017–2026 clean out-of-sample claim follows from these tests.

The all-in fixed trading cost remains exactly **USD 0.40 per ounce per
completed round trip**. Previously exposed BOS/H1 losses are unchanged.
Do not mark Draft PR #1 ready until full CI and original-data replay are
independently verified on the exact candidate commit.
