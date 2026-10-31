# Arithmetic evolution feedback bridge — 2026-10-30

## What is now connected

The repository already had **three separate executable components**:

1. `scripts/run_arithmetic_evolution.py` — deterministic bounded proposals from complete exposed training records.
2. `scripts/materialize_arithmetic_generation.py` — immutable formula files and dispatch index.
3. `scripts/run_arithmetic_dispatch_training.py` — canonical reference/fast execution and independent reconciliation of the trade, weekly, monthly and observed-M1 equity reports.

The new `scripts/compile_arithmetic_training_feedback.py` closes the **evidence feedback edge**: it consumes the *complete* set of frozen annual replay shards, re-runs the actual reference/fast comparison on each, and constructs the next `NRFX_ARITHMETIC_TRAINING_INPUT_V1` containing old evaluated candidates plus the newly evaluated generation. The new candidate identities are added to `explored_ids` to avoid proposing them again.

This is an **offline, training-only** operation. It is NOT a background research daemon, proof of profitable trading, an OOS test, or a broker/tick execution certificate. No raw Gold ZIP, M1 quotes or trade ledger is uploaded.

## Fail-closed contracts

- The original training input and generation manifest must replay deterministically, and the canonical dispatch files must match.
- Every proposed identity must appear **exactly once in every frozen training year**. Duplicate shards, overlapping ordinal windows, missing years, incomplete shards, wrong strategy identities, or a year outside training fail.
- Every annual shard must have the expected source ZIP SHA, canonical `0.40` USD/oz cost, explicit training-only flags, correct generation/input hashes and a PASSED parity claim. The claim is independently checked against both report trees, not trusted.
- The canonical verifier rechecks reference/fast reports, each trade's arithmetic and chronology, observed M1 equity, monthly and weekly exit booking, and exact execution parameters.
- The reference summary must identify the authorized source archive; all formula runs for the same year must share the same loaded BID/ASK fingerprint.
- The feedback input retains exactly the training-year universe, never adds a prospective or untouched holdout year, and refuses an incomplete candidate pool or >128 candidates.
- The next input and an evidence sidecar are published idempotently, without overwriting differing files. The sidecar records source/generation fingerprints, shard index digests, and summary/trade hashes, but **not raw data**.

## Local execution (only after actual authorized replay shards exist)

```bash
python -m scripts.compile_arithmetic_training_feedback \
  --training-input /private/training_input.json \
  --generation-manifest /private/generation_001.json \
  --dispatch-dir /private/dispatch_001 \
  --replay-dir /private/replay_2012_ordinals_1_8 \
  --replay-dir /private/replay_2013_ordinals_1_8 \
  --out /private/next_training_input.json

python -m scripts.run_arithmetic_evolution \
  --input /private/next_training_input.json \
  --output /private/generation_002.json \
  --seed 19 --generation 2 --count 12
```

Supply **every** annual shard for **every** formula and frozen year. The example paths are illustrative only; they do not assert those replays exist. If a shard is missing, compilation refuses to produce an input. No user steps are required to review this implementation; real historical replays still require authorized local data access.

## Verification and limitations

`tests/test_compile_arithmetic_training_feedback.py` exercises the bridge with synthetic replay trees and a stubbed canonical report verifier; this is a test of the completeness, identity, provenance, immutability and next-generation contracts, **not** actual Gold ZIP replay. A passing repository CI run is required before calling the code verified on the PR head.

The previously rejected BOS/H1 strategy remains rejected; no new profitability or independent OOS claims. The original Gold ZIP must remain private. Keep PR #1 Draft and unmerged until exact-current-head source replay and release gates succeed.

The GitHub repository's current visibility must be checked independently; do not assume the word "private" in a task title makes it private.
