# Arithmetic Evolution — training-only research proposals (2026-10-30)

## Scope and status

The deterministic next-generation planner lives at
\`src/norisk_quant/research_evolution.py\`. The offline entry point is
\`scripts/run_arithmetic_evolution.py\`. This is an **experiment proposal
component**, not an autonomous execution loop, an independent out-of-sample
(OOS) evaluation, a proof of market edge, or a live trading system.

Each proposal is a bounded mutation of an existing validated
\`norisk_quant.math_discovery.Formula\`. The engine records its parent identity,
mutated fields, complete formula and SHA256 identity. The manifest includes
the SHA256 of its reconciled training evidence, and its own SHA256. Repeating
the same input, seed, generation, and exclusion set produces identical output.

## Required input

The input JSON envelope must contain **exactly**:

- \`schema\`: \`NRFX_ARITHMETIC_TRAINING_INPUT_V1\`
- \`years\`: a chronological list of at least two complete training years
- \`candidates\`: 1–128 objects, each with **only** \`formula\` and \`records\`
- \`explored_ids\`: an array of unique, canonical SHA256 identities to exclude

\`formula\` must have exactly the frozen \`Formula\` dataclass fields.
\`records\` must have one \`{"year": YYYY, "metrics": {...}}\` object for
each frozen year. Metrics must contain exactly: \`months\` (all 12 UTC
calendar months), \`net_usd_per_oz\`, \`trades\`, \`fees_usd\`,
\`positive_months\`, \`uncertain_gap_trades\`,
\`synthetic_forced_closures\`, and \`accounting\` (\`PASSED\`).

The existing \`training_summary\` function independently reconciles all
years, 12-month calendars, net P/L, counts, and exactly **$0.40/oz** all-in
roundtrip fee per trade before any ranking is allowed. Incomplete or
tampered candidates abort the entire generation. Any extra holdout,
prospective or OOS fields are rejected, rather than influencing selection.

## Offline invocation

After producing a frozen training-only JSON envelope from **verified**
monthly/annual reports:

\`\`\`bash
python -m scripts.run_arithmetic_evolution \
  --input /path/to/frozen_training_evidence.json \
  --output /path/to/generation_0001.json \
  --seed 18 --generation 1 --count 12
\`\`\`

The output is immutable: re-running the identical request returns the
same manifest; changing the request while reusing the same output path
fails instead of overwriting prior evidence. The CLI rejects duplicate
JSON keys, NaN/Infinity, malformed schema and contaminated input. It
does not read market quotes or send orders.

## Ranking and multiplicity limitations

The ranking uses the **existing training-only heuristic** and a
deterministic 60% elite / 40% broader-parent proposal policy. This is
search guidance, **not a significance test**. Repeated exploration can
overfit even if every individual backtest is causally correct. The
existing joint year-block sign-flip diagnostic has explicit assumptions
and does not establish a valid OOS result.

Do not promote a candidate from this component. A separate preregistered,
chronologically later evaluation, source integrity, broker-specific
bid/ask costs, and genuinely independent validation remain necessary.

## Test scope

\`tests/test_research_evolution.py\` and
\`tests/test_run_arithmetic_evolution.py\` cover deterministic generation,
input order invariance, duplicate candidate rejection, year/fee/month
integrity, holdout contamination, SHA identities, prior-ID exclusion,
resume idempotence and immutable output. Synthetic evidence only; no
raw gold archive was uploaded. The planner does not yet schedule or
execute its proposed formulas: the next integration step is a frozen
job queue consuming these manifests and the canonical backtest engine.
