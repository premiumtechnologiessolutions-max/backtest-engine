# Batch 03: full private Terminal -> canonical Data Hub ingestion boundary

Date: 2026-10-30. Draft, read-only. This bridge runs B01 and B02 together on one pinned GitHub checkout; previous PR #5 and #8 remain reviewable upstream proofs.

## Input contract
- File is private local NoRiskFX Terminal v0.19.1 read-only request JSON.
- B01 rejects unknown keys/credentials, non-UTC/nonfinite ticks, duplicate or reversed source sequence, missing historical account conversion and synthetic input without explicit opt-in. B01 preserves exact original bid/ask quotes and quote sequence in RAM.
- B02 independently validates ONLY B01's exact 17-field metadata envelope, binds original raw-byte SHA and source-scoped quote SHA, and registers source family, currency and non-execution status.
- The bridge cross-checks normalized quote count, UTC time endpoints and SHA fingerprints against B01 evidence. It never copies the entire input to Git, web storage or a separate external service.
- With no parameters, the private CLI emits source family, asset, tick count, time bounds, hashed ID and explicit non-trading flags. It DOES NOT print raw prices, account number, broker scope, commissions, passwords or the original data-file hashes.
- Test fixtures are made-up quotations, not actual VT trades or authenticated market observations.

## Operator workflow

Run locally from the installed canonical research checkout on the same private machine as the exported snapshot:

python scripts/verify_unified_source_intake.py /private/XAUUSD-read-only-snapshot.json

No credentials, Oracle access, MT5 order endpoints, external APIs, P/L or execution permission exist in this bridge.

## What the integration DOES NOT do
- It does not infer original historical DST transitions, continuously collect the market, resample ticks, perform strategy backtesting, guarantee a broker fill or forward OOS, authenticate the declared provider, apply $0.40/oz fees, or double-count Terminal's spread/slippage/commission.
- Original Gold M1 and private Terminal ticks remain separate source classes. Future private tests must compare actual short samples without copying either dataset into public Git.
- Public metadata is not an authorization mechanism; any private API later added to Terminal still requires its existing authenticated gateway and row-level privacy protections.
- This branch is a research integration and is NOT to be auto-merged or deployed onto the existing Oracle server, CRM or live trading instances.

## Acceptance
Targeted CI: B01 tests, B02 tests, B03 exact end-to-end tests, M1/tick provenance constraints. Entire canonical pytest suite in a separate CI step. Keep this PR Draft pending independent local original-source validation, licensing constraints and deployment review.

Parent architecture epic: #6. Draft B01: #5. Draft B02: #8.