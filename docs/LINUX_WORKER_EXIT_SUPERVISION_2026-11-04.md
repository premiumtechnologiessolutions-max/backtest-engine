# Linux worker/process supervision — engineering-only exit gate

Construction addition: scripts/durable_worker_process_supervisor.py

This module does NOT spawn, terminate, kill, or automatically schedule
a real research worker. It provides a future Linux offline worker launcher
with a strict **process-group leader identity contract**: boot UUID,
OS PID == process group, and /proc startup ticks, permanently bound to an
existing SQLite-fenced claim. Registration is allowed only while the lease
is current and in RUNNING state.

A Linux /proc inspector is read-only. Requeuing a stuck attempt requires
the lease to be expired, the frozen attempt/process identity to match,
the original boot ID to be unchanged, and the original process plus all
observable live members of its process group to be absent. It requeues
under the SAME SQLite BEGIN IMMEDIATE transaction, with exact fencing
comparison. Crashes, PID reuse, dead process leader with surviving group,
permission errors, boot changes or unregistered processes fail closed
unless an OS exit can be established. Expired leases alone are not enough.

**Hard limits / not production-ready:**
- Linux only. Windows and cloud supervisor integration are missing.
- No launched worker, no process group isolation enforcement, no cgroups,
  sandbox, resource ceilings, credentials isolation or job cancellation.
- A process that escapes the expected process group could evade group
  inspection. A complete launcher must ban daemonization/setsid escape or
  independently track descendants in cgroups / OS Job Objects.
- /proc scanning is not a kernel-issued signed proof; process identity
  observations can race with lifecycle changes. Treat this as the
  construction foundation, not final production acceptance.
- The existing legacy manual requeue API remains available to owner
  tooling; production must route all recovery through a single hardened
  supervisor and remove unsafe shortcuts.
- Tests use a fake OS inspector and synthetic SQLite metadata ONLY. No
  real worker, LEAN/Nautilus engine, Gold research or broker is launched.

No ACCEPTED trading results are produced.
