# Opt-in canonical recovery of interrupted frozen batch outputs — 2026-10-28

## Why this exists

The offline historical batch runner already writes one atomic, source-reconciled manifest entry per completed canonical run. A process can terminate after writing all four canonical ledgers but before publishing its manifest entry. Previously that left a nonempty orphan directory which blocked resumption and could tempt manual deletion/retesting. This change adds an **explicit, default-off** recovery path. It does **not** add a prospective worker or execute any new Gold-data backtest by itself.

## Usage

From the exact clean frozen Git checkout, with the original private archive available locally and matching the frozen SHA256:

```sh
python -m scripts.research_batch_orchestrator --plan /private/frozen-plan.json --out /private/frozen-results --max-jobs 20 --recover-verified-orphans
```

Without the flag, nonempty outputs without a manifest entry remain blocked. With the flag, while holding the existing exclusive output lock, the runner checks the **entire** summary, monthly, weekly and trade ledgers against the frozen strategy specification, original source archive SHA256, exact engine commit, $0.40/oz all-in roundtrip cost, trade dates, observed M1 coverage and accounting invariants. Only a fully passing orphan is durably re-added to the manifest; it is counted separately as `recovered_verified_orphans`, **not** `executed_this_invocation`. Existing accepted manifest records are always re-audited and never silently overwritten. Incomplete, tampered, wrong-source or wrong-commit orphans abort without a promotion; a symlinked runs root is rejected.

## Evidence and limitations

Recovery rechecks the canonical output artifacts; it cannot prove whether the original run was uninterrupted, independently generated, or produced on a real broker. The four ledgers do not themselves establish independently hash-pinned M1 floating equity; monthly floating drawdown remains **N/A** until the separate source-pinned equity audit passes. Historical 2012–2016 experiments are exposed, not clean OOS. A verified orphan is **not a new parameter spec, independent hypothesis, prospective month, or new backtest**. Existing jobs in the frozen manifest retain their original acceptance gates. Tests are synthetic; no original private Gold ZIP was executed in this change.

Keep the PR Draft. Do not upload raw private BID/ASK or Gold ZIP to the public repository, merge the PR, alter billing/privacy, or connect MT5 live.
