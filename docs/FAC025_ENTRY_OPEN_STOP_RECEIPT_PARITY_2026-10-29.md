# FAC025 canonical receipt compatibility with Limit entry-open stops (2026-10-29)

## Verified code-contract mismatch

`src/norisk_quant/limit_engine.py` emits `entry_open_beyond_stop` when a pending Limit entry is triggered on an observed M1 bar whose **opening price is already beyond the configured protective stop**. It records an adverse first-open fill and deducts the canonical **$0.40/oz ALL-IN roundtrip** fee.

`src/norisk_quant/persisted_trade_integrity.py` already recognizes that execution reason and independently requires an adverse fill (not a better-than-stop fill). Before this patch, `scripts/research_fac025_canonical_receipts.py` rejected the same valid engine reason as unknown. Consequently, the research-only FAC025 receipt bridge could reject an otherwise reconciled canonical engine trade.

## Change and synthetic verification

The FAC025 adapter now recognizes `entry_open_beyond_stop` and applies the **same directional adverse-price contract** as `open_stop` and `gap_stop`: for buy trades, exit must not exceed stop; for sells, exit must not be below stop (within existing 1e-7 price tolerance). Entry/exit chronology, geometry, receipt-time causality, independently recomputed gross/net and exact $0.40/oz cost remain enforced.

`tests/test_fac025_entry_open_beyond_stop_receipt.py` adds eight parametrized/negative synthetic checks: buy/sell adverse fills, stop-equality boundary, improved-fill rejection, fee omission rejection, and unknown-reason rejection. The eight cases also passed a **local reconstructed-module** pytest check (8 passed); this is NOT a full-repository run on the GitHub checkout. Full current-head CI, actual original ZIP 13-field replay and new OOS remain unverified.

## Research boundaries

This is **execution-ledger schema compatibility**, not evidence of profitable trades, broker quote execution, authentic receipt timestamps or actual original-Gold-ZIP parity. No source market ZIP was uploaded, no strategy parameters were optimized, no fee was changed, and PR #1 stays **Draft/unmerged**. The repository is currently public, despite the requested private designation; do not upload confidential data.
