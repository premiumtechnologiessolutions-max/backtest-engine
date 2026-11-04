# Backup/restore integration in Quant Engine construction dashboard

The read-only status CLI now accepts --backup-dir for an existing frozen
snapshot created with scripts.durable_backup_cli. Mission control checks
the snapshot with scripts.durable_backup_attestation.verify_durable_backup
and exposes status as VERIFIED_REVIEW_ONLY, NOT_CONFIGURED or INVALID.

Use: python -m scripts.quant_construction_snapshot --design /private/design.json
     --database /private/control.sqlite3 --backup-dir /private/backups/snapshot_001

Load the resulting JSON in web/quant-control/index.html to see backup
status, jobs, attempts and explicit AUTO-RESUME DISABLED. No source ZIP,
backtest, broker, worker or external AI is launched. Snapshot SHA256 is
a corruption detector, not an externally trusted signature.
