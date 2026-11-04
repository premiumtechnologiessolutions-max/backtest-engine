# Durable synthetic supervisor fault receipts

The real (fixed) Linux synthetic worker now has an auditable SQLite
receipt, keyed to the original attempt, OS PID, start ticks, boot ID and
fencing token. The staged receipt includes only bounded hashes, output
byte lengths and fault classifications — no stdout/stderr content.

Staging requires the original live RUNNING lease. Repeated identical
evidence is idempotent; changed or forged receipts fail closed. Read-only
audit rechecks every stored receipt against the immutable process identity
and attempt history. After the lease expires, the existing same-boot OS
group-exit gate remains mandatory for any recovery.

These are engineering-only synthetic fault receipts, not evidence that
LEAN, Nautilus, original Gold, broker pricing or profitable strategies
were ever run. They grant no execution or acceptance authority.
