# FAC025 — machine-checked frozen causal-filter grid (2026-10-29)

The pre-outcome filter-only hypothesis and its parameters were already frozen in
docs/FAC025_FROZEN_CAUSAL_NY_SESSION_RISK_GATE_2026-10-28.md. This patch
adds a deterministic machine-readable enumeration in
scripts/research_fac025_frozen_grid.py, with **72 correlated parameter
settings belonging to ONE hypothesis**, stable per-setting SHA256 identities,
and fail-closed validation. No search, fitting, optimization or historical
outcomes were consulted when defining the enumeration.

Parameter order: lookback {4,8,12}; min normalized M15 range
{0.0004,0.0008}; max normalized M15 range {0.003,0.006}; NY-local daily
realized loss halt USD/oz {2,4,6}; session hours {08–12,09–13} with
America/New_York DST. The string representation of decimal values is
canonical and is **not** a claim of measurement precision.

Frozen grid SHA256 (SHA256 of 72 newline-separated, canonical per-setting
fingerprints, without a final newline):
9646a2d037024f7a18bd97eca3187ccf6404e34f58c713e402c1c407fba3c702.

Run python -m pytest -q tests/test_research_fac025_frozen_grid.py.
The tests pin the digest, verify uniqueness and full Cartesian coverage,
and reject extra/reordered fields, tampered fingerprints, non-grid values,
and bool/int/float substitution. This does not replace immutable source
commit pinning or source-verified data receipts.

**Scientific status:** 0 new original-source backtests, 0 new monthly P/L
observations, 0 new M1 floating-DD measurements, 0 approved strategies.
Entry/exit rules are not yet frozen, and no actual one-slot portfolio
execution or forward/OOS verification occurred. Existing registry totals
remain unchanged. Future workers must not treat these 72 settings as 72
independent hypotheses or select the grid based on exposed years. Before
executing, freeze entry/exit, portfolio capacity and priority policy; run
canonical parity and only then register actual source-verified outcomes.

Exactly $0.40/oz ALL-IN roundtrip and next eligible open <=1 minute remain
non-negotiable execution invariants, not results. No private Gold ZIP, raw
BID/ASK data, broker keys, live trading or external services are involved.
Keep PR #1 Draft and unmerged.
