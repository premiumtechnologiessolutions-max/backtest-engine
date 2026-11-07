# Frozen batch execution-settings provenance gate — 2026-10-29

## Why

The frozen batch orchestrator already requires a canonical fixed **$0.40/oz** all-in roundtrip fee, but its evidence auditor previously accepted a summary whose remaining `settings` fields had been altered or omitted. This could falsely associate a reconciled trade ledger with a different one-ounce, entry-delay, holding-cap, or end-of-data policy. A correct fee by itself is not enough to prove the experiment's execution configuration.

## Change

`scripts/research_batch_orchestrator.py::audit_run` now requires the entire persisted settings dictionary to equal the canonical serialized settings for the frozen CLI run, including **all keys and JSON value types**. The standard preset is `Settings()`: one ounce, 0.40 USD/oz, one-minute maximum entry delay, close at data end, and no holding cap. The predeclared **QS01** exception uses `qs01_settings()`: one ounce, 0.40 USD/oz, zero-minute entry delay, and 30-minute holding cap. Unknown, missing, boolean-masquerading-as-numeric, and noncanonical fields are rejected.

Ten synthetic regression scenarios cover seven field/value mutations, missing/extra keys, and the distinct QS01 preset. This is a **provenance and schema gate**, not proof that raw data or trade fills were genuine.

## Verification and limits

The change and its regression tests were committed atomically to the existing Draft PR branch. The complete current-HEAD pytest/CI, original private Gold ZIP replay, and independent forward validation must be checked separately; do not infer a green suite or a profitable strategy from this commit. The repository is PUBLIC per GitHub metadata, so no raw market data or private ledger is included. PR #1 remains Draft/unmerged.
