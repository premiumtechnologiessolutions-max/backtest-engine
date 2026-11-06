# NO RISK FX | Unified Research Platform | Integration Batch 01

Date: 2026-10-30. Status: read-only integration candidate, NOT production or trading approval.

## Audited existing systems
- NoRiskFX Terminal (PRIVATE) at commit 30e4b52e5ed61adbbd6e7aacab090ce2e1cd57c4: Arabic market research, OANDA, official macro/news, charts, read-only VT Markets Cent historical tick import, initial scalp replay and a private Oracle terminal.
- backtest-engine (PUBLIC) at parent commit 6e1c14cc1277e2283d05050c989ba3805559e2c0: canonical XAUUSD M1 execution, original historical evidence and fixed $0.40 per ounce ALL-IN round-trip research cost.
- aiquantlab (PUBLIC), code inspected at 23afada23cd570f336dab8958b576d675252ec40: agents, scheduling, durable research registry, regimes, research only.
- Local V5.1 research brain: separate release, not fully integrated into canonical GitHub engine.

## Data contracts and safety
1. Never present OANDA candles, original Gold BID/ASK M1 and VT Cent MT5 ticks as one interchangeable authenticated source. Source scope, instrument, candle completion, UTC and contract/currency labels must survive the adapter.
2. This PUBLIC repo must never receive the owner's raw ticks, original Gold ZIP, private broker/account scope, credentials, private SQLite, or trade ledgers. Samples in tests are synthetic. The deployed Oracle terminal is NOT modified.
3. Terminal's tick replay accounts for BID/ASK + explicit commission + slippage + latency, while the canonical M1 engine assumes $0.40/oz ALL-IN for a full round trip. These are different, separately labeled execution scenarios. Do NOT double-charge.
4. The observed VT Cent account uses quote USD, account USC and an independently checked 100 USC/USD factor. Keep historical conversion factors separate, and never assume the same factor or contract/lot definition for all brokers.
5. The Terminal's recent VT clock adjustment is not a generic historical DST normalization pipeline. Only already explicit UTC ticks may cross this boundary. A declared quote is neither a verified fill nor an untouched OOS sample.

## Delivered code
- src/norisk_quant/integrations/terminal_ticks.py: strictly validates Terminal 0.19.1 private input-request JSON, 2 to 250000 real quote ticks, max 80MB. Rejects synthetic by default, duplicate JSON keys, unknown fields, bad timestamps, crossed prices, nonfinite input, missing quote/account currency conversions and unordered sequences. Delegates to canonical normalize_ticks.
- scripts/verify_terminal_intake.py: private offline metadata-only preflight; no MT5/network/order calls and no quote/secret output.
- tests/test_terminal_ticks_integration.py: regression suite for valid source data, explicit USC, deterministic raw/normalized fingerprints, privacy, malformed imports, synthetic opt-in and no strategy-results ingestion.
- .github/workflows/terminal-integration-contract.yml: targeted Python 3.12 regression checks.

Offline usage: python scripts/verify_terminal_intake.py /private/XAUUSD-history.json

The returned source_bytes_sha256 is the exact input-byte SHA; quote_context_sha256 binds contract/account scope and ordered ticks without returning scope. cost_model=NOT_APPLIED_DATA_ONLY, execution=NONE_RESEARCH_IMPORT, source_authentication=NOT_VERIFIED, independent_oos=false.

## Required follow-on work and measurable gates
- Batch 02: private sample replay for XAUUSD and EURUSD, exact quote timestamps/identity/conversion, gap and DST audit, broker-vs-fixed-cost scenario parity, no raw upload.
- Batch 03: integrate AI Quant Lab's agent commands with canonical immutable job IDs, watchdog/restart and bounded queue; inject crash/duplicate-write tests. Agent output is qualitative, not official P/L.
- Batch 04: authenticated read-only research status API for the Terminal UI; access isolation, privacy and audit tests before any Oracle changes.
- Batch 05: repeatable full-length canonical engine tests, original-source reference/fast parity, monthly/weekly audit, multiple-search accounting and untouched prospective observations.
- Batch 06: separate explicit operator-approved rollout, backup restore proof, long-run capacity tests and rollback. Keep existing CRM and Oracle gateway untouched.

Terminal release notes report a historical six-hour sample of 110208 gold ticks and 17499 EURUSD ticks; not fresh independently verified during this integration. No actual or guaranteed profitable strategy is established. Never merge or deploy this integration until applicable quality gates pass.
