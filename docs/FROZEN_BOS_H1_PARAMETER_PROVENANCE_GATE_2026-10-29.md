# Frozen BOS/H1 parameter provenance gate — 2026-10-29

## Finding

The frozen annual runner previously verified the **strategy name**, selected year,
source SHA, M1 fingerprint, fixed fee and annual accounting. However, the
persisted `run_parameters.bos_fib` and `run_parameters.h1` dictionaries were
not independently compared to the originally declared experiment. A changed
default (e.g. Fibonacci level, stop buffer, H1 EMA length, freshness limit,
pivot ambiguity handling, or expiry) could retain the same strategy label and
produce a seemingly certified but *different* experiment.

## Change

- New `scripts/frozen_parameter_contract.py` independently freezes all
  14 BOS/Fibonacci settings and all 3 H1 settings, together with year,
  strategy label, `$0.40/oz` fee and the explicit not-clean-OOS flag.
- Reject missing/extra fields, altered values, or coercible Python types
  (e.g. `True == 1` and `1 == 1.0`). This also catches future dataclass
  defaults added without a deliberate research protocol revision.
- The official `run_bos_fib_frozen_sensitivity.py` now calls the independent
  gate **after persisted summary equality and ledger/source checks** and
  **before publishing** the atomic multi-year evidence directory.
- Synthetic tests cover the unchanged frozen snapshot, every individual
  BOS/H1 setting, extra/missing keys, type coercion, annual year identity,
  and the OOS disclaimer.

## Scope and limits

This is a **parameter-provenance and fail-closed reporting** improvement,
not a strategy optimization or evidence of profitability. The frozen strategy
and execution settings were not changed. The authorized original
`Gold data.zip` SHA-pinned 13-field replay has **not** been rerun on this
commit, and no fresh independent OOS or broker-tick validation was performed.
The repo is reported PUBLIC: do not commit raw quotes, ZIPs or trade ledgers.
Keep PR #1 Draft/unmerged until source replay and full acceptance gates pass.
