# External adapters — construction-only contract (2026-11-04)

All six external components are represented by inert static metadata only:
LEAN, NautilusTrader, OpenBB, RD-Agent, TradingAgents, FinRL.

The registry **does not import** third-party code, access a network, fetch
market data, run subprocesses, launch workers, place orders or conduct research.
It intentionally rejects any request to enable operational capabilities.
The listed input/output names are future integration interface placeholders,
not claims of compatibility with actual upstream APIs.

The engineering acceptance requirements before any separate owner authorization:
1. Review pinned upstream source and licenses; record exact commit/version.
2. Design and test a sandbox boundary, no secrets, no network by default.
3. Verify deterministic synthetic schema mapping and refusal of malformed data.
4. Connect to the frozen job/fencing state machine and unverified receipts.
5. Define resource quotas, cancellation, provenance, restart recovery.
6. Require independent evidence audit; unit tests alone are insufficient.
7. Keep production execution, real Gold replay and OOS disabled until the
   complete platform is reviewed and the owner grants new explicit approval.

Tests are synthetic static-only checks. No market evidence is produced.
