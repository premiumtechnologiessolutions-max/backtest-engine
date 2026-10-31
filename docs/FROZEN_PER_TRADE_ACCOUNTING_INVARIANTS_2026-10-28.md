# Frozen 15-field trade-ledger independent accounting gate (2026-10-28)

## Scope

The frozen annual runner previously checked the exported CSV against the in-memory executor's 15 trade fields, then reconciled annual/monthly/weekly totals. That catches mismatched exports, but it cannot detect the **same** accounting corruption in both ledgers. In particular, two trade fees of 0.50 and 0.30 can sum to the expected 0.80 for two 1-oz trades while each trade violates the frozen $0.40/oz contract.

The validator in `src/norisk_quant/persisted_trade_integrity.py` now reconstructs **both** execution and exported ledgers independently, row by row, after field parity:

- positive ounces;
- each trade cost equals `0.40 * ounces` within absolute floating-point tolerance 1e-9 (not an aggregate-fee-only check);
- `gross_pnl == side * (exit_price - entry_price) * ounces` within 1e-7;
- `net_pnl == gross_pnl - cost` within 1e-7;
- `signal_at <= entry_at <= closed_at` (timezone-aware timestamps were already required by the parity gate).

The new synthetic regression module `tests/test_persisted_trade_accounting_invariants.py` covers matching fee, gross, net, quantity and chronology corruption; offsetting per-trade fee errors that preserve annual totals; and a valid 2-oz execution.

## Verification and limitations

Seven focused tests were reproduced locally with a manually reconstructed copy of the validator under Python/pandas and **7/7 passed**. This is a scoped isolated smoke check, **not** a full test of the actual GitHub checkout or CI. The test module and production validator have been committed to `feat/quant-engine-foundation`; run the full pinned GitHub test suite on the exact final HEAD before claiming release acceptance.

No original Gold data.zip was available in this environment. No actual-source annual replay, 13-field original-archive comparison, new OOS result, tick execution certification, or new profitability result is claimed. The original source SHA-256 and frozen $0.40/oz cost remain unchanged. No raw quotes or archived trade ledgers were uploaded. PR #1 must remain Draft and unmerged.


## Matching protective-price corruption negative controls (2026-10-28)

The independent 15-field trade-ledger validator also requires positive entry,
exit, stop and target prices, and the frozen `LimitOrder` protective geometry:
long `stop < entry < target`, short `target < entry < stop`. This
catches matching corruption in both in-memory and persisted ledgers even when
P/L and fees are arithmetically consistent. An exit **beyond** the stop remains
valid for an adverse observed gap-through, and short-side trades remain valid.
Ten new synthetic parameterized/control cases are included; this is **not**
broker/tick certification, prospective OOS or original-source replay.
