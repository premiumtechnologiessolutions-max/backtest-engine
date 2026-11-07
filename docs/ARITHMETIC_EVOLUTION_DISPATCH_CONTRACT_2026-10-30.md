# No Risk FX — Replay-verified arithmetic evolution dispatch

Date: 2026-10-30. Status: research-only, training-only, **not an OOS result**.

## Why this bridge exists

`scripts/run_arithmetic_evolution.py` produces an immutable training-only
proposal manifest, while the canonical backtest CLI accepts individual
`--formula-json` files. The dispatch bridge connects these **without
interpreting a proposal as a tested or profitable strategy**.

## Frozen offline workflow

First generate a training-only evolution manifest from complete, reconciled
annual training records (not raw market quotes):

```bash
python -m scripts.run_arithmetic_evolution \
  --input training.json --output generation.json \
  --seed 17 --generation 1 --count 12
```

Then replay the evolution **from the original training evidence** and
materialize one canonical CLI-compatible Formula JSON per proposal:

```bash
python -m scripts.materialize_arithmetic_generation \
  --training-input training.json \
  --generation-manifest generation.json \
  --output-dir frozen_generation_1
```

Each `formula_NNN_<identity-prefix>.json` contains only the frozen Formula
fields; it is compatible with the canonical `norisk backtest --strategy
arithmetic --timeframe M1 --formula-json <file>` command. The exact data
archive, date window, execution engine, source SHA and output destination must
still be pinned by the downstream research batch. No market-data access or
backtest occurs during materialization.

`dispatch_index.json` records each formula's full identity, parent identity,
file SHA256, training input SHA256, generation manifest SHA256, and the exact
research fee policy ($0.40 per ounce all-in roundtrip).

## Fail-closed properties

* Strict JSON parsing rejects duplicate keys, NaN, Infinity and oversized files.
* Replays the **entire deterministic generation** from original training input;
  checks type-preserving canonical JSON equality, not just self-reported hashes.
* Rejects changed source evidence, formula parameter types, missing/extra
  generation fields, mismatched proposal identities and altered rankings.
* Never overwrites an existing file, symlink or unexpected output directory
  entry. A partial publish can be resumed without changing completed evidence.
* Index is published last. An absent index means incomplete dispatch.
* Proposals are **not executed**. No broker connection, order, trading
  authorization, independent OOS claim, or market-edge certificate is issued.

A matching SHA256 or deterministic replay establishes *internal consistency*,
not independent authenticity of the original data, economic validity, or a
profitable trading strategy.

## Outstanding gates

1. Execute this bridge against a frozen real training manifest, then run each
   formula through canonical Reference and Fast engines with identical data.
2. Reconcile trade-level fields, equity, fees, monthly and weekly ledgers.
3. Keep previously examined 2012–2026 samples marked as historically exposed.
4. Freeze a prospective validation period before seeing its outcomes.
5. Do not promote PR #1 from Draft or authorize live trading based on training.

No raw Gold ZIP, private quotes, or broker credentials belong in Git.
