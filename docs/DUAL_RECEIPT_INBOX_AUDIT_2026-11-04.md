# Two receipt staging formats — coordinated watchdog

A concurrent construction change introduced a second, metadata-only inbox
at scripts/unverified_receipt_inbox.py. It stores a caller-declared
artifact SHA256 but not artifact bytes. The new byte-backed transactional
stage at scripts/durable_external_receipts.py retains bounded actual bytes.

**Neither is independently audited trading evidence**, and neither marks
a research result ACCEPTED. The module
scripts/durable_receipt_inventory.py audits BOTH formats using one
read-only SQLite snapshot supplied by the operations gate. Any
unverified staged receipt requires OPERATOR_ATTENTION; a tampered stored
digest, stale identity or disconnected attempt yields INVALID.

The stage formats are currently distinct and not a production integrated
two-stage workflow. We must unify API and archival policy during later
engineering review before enabling external workers. The staged byte
format is stronger for independent evidence integrity because it checks
actual artifact bytes. The metadata-only format is weaker and cannot be
treated as original source or execution evidence.

All tests are synthetic. Original Gold archive runs, provider requests
and market backtests remain forbidden by the owner's engineering freeze.
