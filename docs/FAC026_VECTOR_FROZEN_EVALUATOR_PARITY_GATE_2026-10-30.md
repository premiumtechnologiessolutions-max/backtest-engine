# FAC026 frozen vectorized/evaluator signal-parity gate — 2026-10-30

**Scope: engineering implementation and synthetic tests, not a new market result.** This audit is a follow-up to the preregistered FAC026 original-source structural screen. FAC026 remains structurally rejected as a standalone positive-every-month candidate (13/24 historically exposed months had no candidate in the 16-variant union).

The optional \`--parity\` mode in \`scripts/research_fac026_original_source_structural.py\` compares **every vectorized structural positive** to the independently implemented frozen \`evaluate\` function. It also compares a deterministic month-stratified sample of nonpositive completed M15 boundaries. It uses actual observed M1-derived M15/H1 bars, requires complete contiguous causal context, and passes no future bar or closed-trade P/L to the evaluator. The original source ZIP SHA256 is checked before reading the archive. Only aggregate counts are output; never commit raw BID/ASK quotes or per-timestamp receipts.

Run locally with private data:

\`\`\`bash
python scripts/research_fac026_original_source_structural.py "/private/Gold data.zip" --parity --out "/private/fac026_parity_aggregates.json"
python -m pytest -q tests/test_research_fac026_original_source_structural.py
\`\`\`

**Limits:** A sampled negative check is not exhaustive negative parity. Structural intent parity does not establish executable next-open fills, stop-first, adverse gap-through, the fixed $0.40/oz roundtrip cost, one-slot portfolio P/L, month-local M1 floating drawdown, broker tick parity, or prospective OOS. The two daily-loss halt settings remain untested without an actual chronological trade ledger. 32 correlated frozen parameter specs represent ONE hypothesis.

**Status at implementation:** no original-source parity execution claimed here; positive/negative parity counts N/A until the private local run is completed and reconciled. No strategy backtests or new monthly net results. Keep Draft PR #1 unmerged.
