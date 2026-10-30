# No Risk FX — B11 scientific rejection decisions
Date: 2026-10-30. Research-only, private operator use, no deployment.

## Purpose
Protect scientific evaluation from relabeling already-exposed losing strategy
settings as a new AI discovery. A strategy fingerprint includes canonical
asset, numeric parameters, timeframe, reference execution, $0.40/oz all-in
research cost, unit size and identity version. It deliberately excludes
agent/campaign names, dataset window and Git commit: two re-runs of the
same trading algorithm settings must not pretend to be independent findings.

B11 cannot infer economic equivalence when algorithm source code changed
but parameters did not. Its conservative matching blocks identical
parameter identities pending independent operator source-parity review.

## Actual private evidence boundary
Owner-private 2012 + 2024 original Gold M1 full-year outputs from B10 were
independently audited by B09 and entered in a PRIVATE scientific journal.
Only redacted engineering counts and loss conclusions are documented
in the PUBLIC repo; NO original market quotes, private price fingerprints,
account scope, real trade ledger or SQLite DB may be committed.

- 2012: 4859 simulated reference trades, 0/12 positive months, -$1527.19
- 2024: 9032 simulated reference trades, 0/12 positive months, -$3406.66
- Combined 13891 historical transactions, 0/24 positive months, -$4933.85
The prescribed fixed research fee is $0.40/oz all-in per round-trip. These
are NOT executable broker fills, independent OOS or live account results.

## Implementation
- evidence_from_audited_year() re-runs B09 exact on-disk proof then reads
  all 12 ordered original monthly ledgers, checking fees and counts.
- ScientificDecisionJournal maintains POSIX owner-only (0600/0700) SQLite
  chained evidence with atomic append and idempotent duplicates.
- candidate_gate(plan) conservatively blocks any exact strategy fingerprint
  previously marked as unsuccessful for monthly net profitability; altered
  parameters become historical-exposed family variants, never unseen OOS.
- The SHA chain detects accidental/local tampering, NOT privileged
  wholesale rewriting. No independent external timestamp/anchoring.
- The operator CLI refuses missing evidence, can't self-approve an
  agent's P/L or broker fill and cannot execute or route any orders.

The gate must be integrated into AI hypothesis dispatch as a pre-execution
control before it can enforce all incoming agents. This module alone is
NOT a complete automatic multi-agent routing boundary.

## Scientific requirements outstanding
1. Prospective frozen candidate selection and untouched future-period
   holdout, with trial-count/multiplicity accounting.
2. Original source and broker fill parity, sensitivity to cost assumptions,
   calendar gap classification and independent source certification.
3. Independently audited code-implementation parity for native AI QuantLab
   hypotheses; no automatic mapping to canonical Gold allowed.
4. Re-run full GitHub Actions on exact review head before accepting PR.
5. Do NOT deploy to Oracle, update MT5 or authorize real/paper orders.

See B10 PR #16 and platform architecture issue #6.
