# No Risk FX — B12 prospective holdout governance (Draft)
Created 2026-10-30. Research-only source, no trading or Oracle changes.

## What B12 fixes
The research engine may evaluate large numbers of historical hypotheses,
including failed models, but it must NOT re-use the SAME FUTURE WINDOW
for iterative parameter choice and then claim independent OOS evidence.

- Versioned immutable local protocol pins Gold XAUUSD M1 asset, full
  original-source SHA, 40-character engine Git commit, strategy's
  complete numeric specification SHA, fixed $0.40/oz all-in cost,
  last exposed training point, and exact UTC prospective window.
- A study must be recorded at least 48 hours before the first
  future observation (embargo) and before the future window starts;
  window begins/ends at full calendar-month UTC boundaries.
- Exactly ONE final prospective candidate may be registered for a
  particular frozen study. Further parameter/data/code changes are
  rejected. Repeated identical registration is idempotent; trial
  attempts use a sequence/hash-chain.
- During future data collection status is FUTURE_NOT_OBSERVED.
  Even after the study concludes, the only status becomes
  MANUAL_INDEPENDENT_AUDIT_REQUIRED, not profitable/approved.
- Private POSIX 0600 SQLite journal in an owner-only 0700 directory.
  Hash-chain is local, NOT externally timestamped or immune to
  a privileged operator rewriting all of the evidence.
- Prototype **does not** import real future data, run strategies,
  authenticate a broker, certify an OOS result or authorize orders.

## Prospective example (synthetic protocol test, NOT real registration)
Registration timestamp (TEST ONLY) 2026-10-30 00:00 UTC.
Suggested untouched future window: December 1, 2026 00:00 UTC
through March 1, 2027 00:00 UTC EXCLUSIVE.
This avoids treating the already considered November 2, 2026
study's first partial market month as a full calendar month.
No existing previously frozen research plan is rewritten.

All the parameters in the sample tests are synthetic, not an
endorsed Gold trading algorithm or a private source SHA.

## Important independence boundary
Passing tests of the registration logic is NOT a third-party scientific
pre-registration or independent proof of a trading edge. Before a real
new prospective study is registered, a candidate needs to be selected
in a documented historical search, independently verified on held-out
past windows, and all attempted configurations logged to control
multiple-testing bias. The only attempted B10 M1-sweep variant was
rejected on 24/24 historically losing months.

There is no proven profitable model and there is no live/paper trading
approval. Keep PR draft. No user/private raw market prices, MT5 account
credentials, Oracle or cloud changes.
