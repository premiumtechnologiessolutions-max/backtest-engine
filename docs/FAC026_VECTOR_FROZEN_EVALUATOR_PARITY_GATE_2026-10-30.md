# FAC026 frozen vectorized/evaluator signal-parity gate — 2026-10-30

**Scope: engineering implementation and synthetic tests, not a new market result.** This audit is a follow-up to the preregistered FAC026 original-source structural screen. FAC026 remains structurally rejected as a standalone positive-every-month candidate (13/24 historically exposed months had no candidate in the 16-variant union).

The optional \`--parity\` mode in \`scripts/research_fac026_original_source_structural.py\` compares **every vectorized structural positive** to the independently implemented frozen \`evaluate\` function. It also compares a deterministic month-stratified sample of nonpositive completed M15 boundaries. It uses actual observed M1-derived M15/H1 bars, requires complete contiguous causal context, and passes no future bar or closed-trade P/L to the evaluator. The original source ZIP SHA256 is checked before reading the archive. Only aggregate counts are output; never commit raw BID/ASK quotes or per-timestamp receipts.

Run locally with private data:

\`\`\`bash
python scripts/research_fac026_original_source_structural.py "/private/Gold data.zip" --parity --out "/private/fac026_parity_aggregates.json"
python -m pytest -q tests/test_research_fac026_original_source_structural.py
\`\`\`

**Limits:** A sampled negative check is not exhaustive negative parity. Structural intent parity does not establish executable next-open fills, stop-first, adverse gap-through, the fixed $0.40/oz roundtrip cost, one-slot portfolio P/L, month-local M1 floating drawdown, broker tick parity, or prospective OOS. The two daily-loss halt settings remain untested without an actual chronological trade ledger. 32 correlated frozen parameter specs represent ONE hypothesis.

## Verified work and precise provenance boundary

The original private ZIP was locally SHA256-verified. A **locally reconstructed independent implementation** of the frozen vectorized scanner and causal evaluator was run separately for 2012 and 2013, without exporting quote rows. It agreed on **24 / 11 variant-level positive decisions** and **1,536 / 1,536 sampled negative decisions**, respectively: **35 positive checks, 3,072 negative checks, zero observed mismatches**. The 35 positives overlap across parameter variants; they are **not 35 independent trades** (the original source structural report identified only 18 distinct candidate timestamps). Deterministic local aggregate SHA256: \`8c15a9ab4beba5023fadd3aa98205ba9774c3b5acccdf2d28fbe96695cda7adf\`.

**Important limitation:** this private-source execution used a locally reconstructed implementation, **not a checkout of the exact GitHub commit**. It must not be called official-checkout parity. The new GitHub implementation was independently tested with synthetic positive, negative, fabricated-signal, and invalid-budget cases. Exact executable commit \`8d876e90a42b4b38789f82b2d6d75a98cf23ceb1\` passed [Engine quality gates 41026023390](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41026023390) (**2,970 tests passed, 1 warning**) and [Quant Lab 41026029794](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/41026029794). An exact-checkout original-source run of \`--parity\` is still required.

**New executed strategy backtests: 0.** Monthly realized P/L: **N/A**; worst month: **N/A**; floating M1 drawdown: **N/A**; approved strategies: **0**. This audit does not retune FAC026 or reverse its structural sample-size rejection. Keep Draft PR #1 unmerged.
