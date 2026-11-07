# External research receipts — single logical identity, two storage formats

Owner policy: **ENGINEERING ONLY**. No market backtests, external executable
runs or acceptance of results before the full engine is built.

The repository currently has a legacy metadata-only SQLite receipt table and
a stronger, bounded byte-backed receipt table. They are NOT two separate
research experiments when they represent the same durable attempt.

This change implements cross-inbox consistency:
- In BOTH staging methods, under the same SQLite write transaction as the
  insert, reject an already-present counterpart if request ID, attempt ID,
  fencing token, frozen binding SHA256, provider receipt SHA256 or actual
  artifact SHA256 disagree.
- During one read-only WAL operational snapshot, validate each inbox and
  compare any mirrors. Conflicting mirrors fail the operational gate
  `INVALID`; correct but unverified records require `OPERATOR_ATTENTION`.
- Report `logical_unverified_attempts` alongside both physical row counts
  and `mirrored_attempts`. Avoid interpreting 2 physical rows as two
  independent research results.
- Retain historic receipts even if an attempt is fenced/requeued; neither
  table grants execution authority, approval or broker access.

LIMITATIONS: the metadata-only table stores a declared artifact digest, not
its bytes; not independently attested evidence. The byte-backed table is
limited to 1 MiB synthetic-sized artifacts. Provider output can be fabricated
and matching hashes do not prove original quote provenance, actual fills,
profitability or OOS. This is NOT an independent acceptance gate and does not
merge the two tables physically. A later schema migration plus isolated
runner supervision and evidence audit remain required.
