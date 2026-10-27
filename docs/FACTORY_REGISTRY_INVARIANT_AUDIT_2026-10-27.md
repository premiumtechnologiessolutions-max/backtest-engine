# Strategy factory registry: fail-closed arithmetic audit — 2026-10-27

## Scope and motivation

The factory contains historically exposed 2012/2013 parameter grids, rejected all-zero experiments, and negative feasibility controls. A naive sum of all parameter executions would inflate the count of **active M1 strategy backtests**, while omitting zero-trade trials would hide negative findings.

`scripts/audit_strategy_factory_registry.py` reads **only** the public `research/strategy_factory_registry.json`. It recomputes executed, active, zero-trade, distinct-spec and monthly totals and fails closed on duplicate experiment IDs or runner paths, contradictory counts, malformed integer fields, missing monthly reconciliation, an altered original-ZIP SHA256 contract, fee drift, or a claim that the exposed design registry is clean OOS. `tests/test_strategy_factory_registry_audit.py` exercises the current registry plus corrupted synthetic copies.

## Current reconciled baseline (not new backtests)

| Metric | Registry |
| --- | ---: |
| Correlated parameter specifications (excluding the original all-zero FAC005) | 287,184 |
| Active annual M1 backtests with filled trades | 553,196 |
| Active exit-booked monthly P/L values | 6,638,352 |
| All annual parameter executions, including zero-trade negative controls | 625,668 |
| Zero-trade annual executions excluded from active total | 72,472 |
| Zero-trade parameter specifications excluded from distinct-spec total | 31,576 |
| Completed active research families | 12 |
| Parameters positive in every month of both design years | 0 |

FAC005's original 51,200 all-zero annual runs and FAC012-A's 100 zero-trade feasibility runs remain visible as negative controls; FAC011/FAC014/FAC016 zero-trade annual runs remain in executed but not active counts. The 287,184 parameter specifications are **not independent statistical hypotheses**.

## Command and limitations

```bash
python scripts/audit_strategy_factory_registry.py
pytest -q tests/test_strategy_factory_registry_audit.py
```

This is a **metadata arithmetic invariant**, not independent execution proof. It cannot verify the original private Gold ZIP, 13-field trade-ledger parity, signal chronology on real data, live spreads, drawdown accuracy, or prospective performance. The original ZIP is absent from this run's accessible Library files and must never be uploaded to this public repository or GitHub Actions. No new strategy grid was run; no monthly-profit result changed. The Draft PR stays unmerged, and the fee contract remains exactly $0.40/oz ALL-IN roundtrip.

The latest successful CI must be tied to the **exact final commit** before marking this audit CI-verified.
