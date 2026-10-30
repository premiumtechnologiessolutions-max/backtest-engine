# Batch 13 — fail-closed scientific rejection gate in private worker

Date: 2026-10-30. **Draft research-only**.

The historical backtest worker is no longer merely accompanied by an
advisory scientific rejection index. Its PRIVATE OPERATOR --execute
command now REQUIRES an existing POSIX-private rejection journal.
Missing/invalid journal causes immediate failure before claiming work.
The worker itself accepts an optional journal object for compatibility
with pre-existing synthetic tests and internal helper use, but every
actual operator --execute path passes the mandatory journal.

The specific rejected `m1-sweep` Gold parameter fingerprint from
B10 full-year private original source evidence (2012, 2024) has
zero positive months in 24 and is blocked before expensive source ZIP
preflight or official simulation, regardless of AI campaign naming.

After independently auditing the historical result, the worker
re-evaluates the scientific journal's decision and chain head.
If another negative result is registered during long execution,
the work is rejected rather than marked completed under stale rules.

Rejections are fail-closed and require operator investigation.
A negative historical decision remains historical-exposed evidence,
not proof that all possible variations of this strategy family fail.
A changed strategy and parameters may still require independent
scientific review and does NOT automatically become future OOS.

No live trading, MT5 orders, Oracle changes, automatic strategy
promotion, broker fill parity or untouched forward validation.
Gold history, original source ZIP, private negative journal and
trade CSV files are never uploaded to PUBLIC GitHub.

## Security limitations
- The local evidence chain is NOT externally anchored and does not
  withstand arbitrary privileged administrator rewrite.
- The direct Python helper's optional journal is for backwards
  compatibility. Only the operator CLI enforces it as mandatory.
  A future authenticated Research Terminal worker API must enforce
  journal checks inside its own production entrypoint.
- Private output execution is currently restricted to reviewed POSIX
  owner-only files; native Windows NTFS permissions remain pending.

Related B11 #17, B12 #18 and unified platform epic #6.
