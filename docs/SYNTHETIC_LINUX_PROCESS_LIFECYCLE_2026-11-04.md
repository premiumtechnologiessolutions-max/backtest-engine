# Fixed synthetic Linux process lifecycle rehearsal

The existing future Linux supervisor previously tested OS process exit
only through fake inspectors. This implementation starts a **single hardcoded
synthetic standard-library SHA256 child** in its own process session,
captures Linux /proc identity, attaches it to the fenced SQLite claim,
observes successful exit, and verifies the process group has no live members.
An additional synthetic regression proves that after the lease expires
the now-exited attempt is eligible for safe single-winner requeue.

Entry point: scripts.synthetic_process_lifecycle_probe.synthetic_process_lifecycle_probe

Only the fixed in-code marker is ever passed to the child. The child is
started with Python -I -S, clean environment, temporary work directory,
process group isolation, a bounded wall deadline and self-applied CPU/
address-space limits. No user-provided shell command, Python code,
strategy file, broker account, market quote or vendor package is accepted.

**Not a production security sandbox:** the fixed child applies RLIMIT
after Python process startup; no cgroups, OS network namespace, systemd
service hardening, seccomp, Windows Job Objects or full descendant tracking
are implemented. No claim is made that untrusted LEAN/Nautilus processes
can safely run within this rehearsal. Only the inert engineering probe
runs; it does not authorize research, publish results, or auto-requeue.

The Linux CI exercises true OS identity; Windows requires a separate
cross-platform supervisor module before production readiness.