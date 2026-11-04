# Durable cross-engine comparison evidence — engineering only

The native-LEDGER comparison from norisk_quant.cross_engine_parity now
has an immutable SQLite inbox. It stages a recomputed summary rather than
raw trade prices, using an active RECONCILING attempt and matching
frozen source commit / UTC evaluation period. Fencing token and worker
identity are checked inside the same write transaction as publication.

The inbox cannot accept an externally supplied success flag, accept
backtests, or launch a provider. Every row remains UNVERIFIED_ONLY.
Repeated identical comparisons are idempotent; changed results, stale
claims, missing candidates and mismatched source periods are rejected.
A read-only audit checks canonical summary serialization, hashes,
frozen attempt history and explicit no-acceptance status.

The stored hash does not cryptographically authenticate external engine
source bytes or independently rerun original trade ledgers. Those
controls remain a later acceptance requirement. No original Gold data
were accessed by these synthetic CI tests.