# Batch 02 | Unified Data Hub: immutable evidence registry

Date: 2026-10-30. Status: review candidate. Standalone batch rooted on the canonical quant research branch, separate from B01 Terminal adapter PR. No Oracle server, private account, original Gold ZIP, raw tick feed or public site was changed.

## Why this exists
Three distinct research contexts must retain explicit source identity:
1. User-provided XAUUSD M1 BID/ASK OHLC: its own original archive SHA256, normalized observed price-slice SHA, gaps, and M1-only event limits.
2. Private NoRiskFX Terminal 0.19.1 VT Cent tick snapshots: Windows-only, read-only MT5 adapter, typically recent 1–6-hour batches. USC and USD may not be silently interchanged. Adapter metadata does not prove broker authentication.
3. OANDA and macro/news data in Terminal: freshness and release vintages require separate future adapters. This batch does NOT treat them as Gold M1 or VT ticks.

## Delivered APIs
- register_original_gold_m1(metadata): requires exact original source SHA and normalized M1 price-slice SHA computed by the canonical engine. It does not itself read or authenticate the original private ZIP.
- register_terminal_tick_evidence(metadata): only the exact read-only B01 adapter evidence contract; rejects scope/credentials, fake OOS/fill/live claims and synthetic data unless opted in.
- SourceRecord.internal_manifest() and verify_record_manifest(): hash-pinned reproducible normalized source manifest, fail closed on tampering.
- SourceRecord.public_summary(): privacy projection excluding provider scopes/names, account currency labels, file SHA and quote SHA.
- SourceRegistry: idempotent in-memory catalog; durable storage not implemented here.
- compare_source_windows(a,b): source-aware observational comparison conditions, no merging and no broker-fill parity.

## Research and privacy invariants
- Source registry handles metadata only, not prices, trading execution or fees.
- Source legitimacy is NOT_VERIFIED; normalized source time must explicitly be UTC. Never infer VT seasonal server offset from old quote timestamps.
- Original M1 bars are not Tick Bid/Ask; overlapping periods allow only source-differenced observations.
- Fixed canonical $0.40/oz all-in roundtrip is an execution research scenario, different from Terminal's quote/spread/slippage/commission model. No cost policy attaches to raw market data.
- Do not commit any raw Gold ZIP, broker-scoped raw ticks, login, private trade ledger, Oracle configuration or licensed data in the PUBLIC repo.
- Neither source class grants independent OOS, live execution, paper trading, strategy success or confirmed broker fills.

## Next integration gates
1. Locally create B01 TerminalTickImport.evidence and pass only its metadata into this registry.
2. Canonical Gold loader supplies sha256_file(source_path), fingerprint_loaded_m1(frame) and exact observed UTC bounds, kept private.
3. Authenticate and authorize a future private catalog API. This public_summary method by itself is NOT an authorization control.
4. Add macro data release-vintage contracts, provider permissions/licenses, unbroken historical DST handling, source gap audits, and budgeted 24/7 collectors in later independent batches.
5. Pass targeted and full repository GitHub Actions checks, then independently audit private historical XAUUSD/EURUSD sample before any merge/deployment.

Not yet delivered: broker connection, data lake, persistent database, actual feed reconciliation, real tick replay parity, auto-agent integration, terminal UI or verified profitable model.