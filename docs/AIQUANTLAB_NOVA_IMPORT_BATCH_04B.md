# Batch 04B: Native Nova HypothesisRecord to canonical research queue
Status: review-only, offline, safe by default. Date: 2026-10-30.

## Source contract
AI Quant Lab V4's InstitutionalResearchStore.hypothesis(id) returns
HypothesisRecord. Its model_dump(mode='json') uses the fields
hypothesis_id, campaign_id, proposed_by, strategy_name, parameters,
statement, economic_rationale, falsification_criteria, compatible_regimes,
parameters_locked_before_test, created_at.

A separate operator context supplies exact XAUUSD dataset SHA, canonical
engine Git SHA, AI Quant Lab Git source commit SHA, timeframe, explicit
UTC window, research quantity and fixed $0.40/oz all-in research fee.
Never invent source hashes or infer a local file path.

## Private operator workflow
- Export the frozen HypothesisRecord object as JSON from AI Quant Lab on
  your PRIVATE research machine. Do not commit source or market quotes.
- Save a separate private context JSON with all exact keys in
  AIQUANTLAB_CONTEXT_KEYS in research_control_plane.py. An independently
  validated input-source manifest and pinned Git commits must supply hashes.
- From the canonical engine checkout:

    python scripts/import_aiquantlab_hypothesis.py --hypothesis LOCAL_HYPOTHESIS_JSON --context LOCAL_CONTEXT_JSON --queue-db PRIVATE_RESEARCH_SQLITE3

- The command only prints a stable experiment ID, state, and no-trading
  research flags. Queue initially PAUSED; it cannot auto-start on import.
- Cosmetic AI commentary or repeated Nova campaigns cannot create
  artificial independent tests or change canonical results.

## Strict boundary
- The local intake never queries an MT5 account, submits orders, or runs a
  backtest. No Oracle changes, publish, execution approval, P/L or proof
  of profitability. Data source hashes are declared, not authenticated.
- AI Quant Lab's native FX strategy names are NOT equivalent to canonical
  Gold strategies. Candidate ID is a SHA-derived namespace over the FULL
  native AQL strategy name and entire immutable AQL source Git SHA.
  A separate independently audited strategy implementation is required.
- Forge V4 evolution proposals have a different source model from Nova
  hypotheses; this adapter rejects Forge-as-Nova input.
- A queue completion means UNVERIFIED artifact recorded, NOT a validated
  strategy or broker fill. Official execution and OOS gates remain separate.
- The queue DB and source JSON remain local private operator files, not
  a public service. Public summaries deliberately redact source/private
  payloads, parameters, tokens and untrusted AI commentary.
