# Quant Research Queue — local integrity hardening (2026-10-28)

This patch strengthens **offline request intake only**; it does not run a backtest, execute a worker, fetch data, or create any profit/loss result.

- Reject queued JSON records with permissive POSIX file permissions, wrong ownership, symlinks, hardlinks, nonregular files, or excessive size, including the idempotent enqueue path.
- Validate frozen family, source commit, spec path, hash formats, ISO dates, and strict integer schema version **even if an attacker recomputes the record checksum**.
- Keep owner-only 0700 queue directory, 0600 files, exclusive atomic creation, fixed QUEUED_NOT_EXECUTED status and no execution hooks.
- Add synthetic regression tests for chmod, hardlink, symlink, and recomputed-hash malformed records.

The SHA256 fingerprint detects accidental changes and binds request metadata; **it is not a digital signature or proof of a trustworthy source commit, GitHub CI, or a completed run**. An attacker with write access to the same user account can replace records. OS-level protection against concurrent hostile path replacement is not fully established; a future worker requires directory-descriptor-based operations, permissions, locks, checkpoint verification and explicit resource limits.

No new XAUUSD backtests or monthly P/L were performed. Registry totals are unchanged. Do not use the queue as evidence of prospective OOS or profitable strategies. Keep PR #1 Draft/unmerged and raw Gold BID/ASK outside the public repository.
