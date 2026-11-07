# Failure-mode supervision of fixed synthetic workers

`scripts.supervised_synthetic_fault_lab.supervised_synthetic_fault_probe`
is a concrete Linux subprocess lifecycle test, not a vendor adapter.

It launches an immutable Python standard-library-only child in a dedicated
process group, binds its real PID/start ticks/boot UUID to an existing
SQLite-fenced RUNNING attempt, and releases a fixed one-line command only
after identity attachment. It uses nonblocking selectors to bound each of
stdout/stderr to 1,024 bytes, a monotonic deadline, and explicit process
group termination/reaping. After every scenario it requires Linux OS proof
that the same-boot process group no longer exists.

Synthetic fault cases: SHA256 happy path, nonzero exit, stderr with nonzero
exit, too much stdout, and a sleeping/hung child. CI proves errors do not
mark results accepted and do not requeue leases without separately proven
expiry. No user-supplied commands, code, file paths, vendor executable or
trading strategies can be launched through this test harness.

**Not a secure sandbox** for untrusted engines: no network namespace,
seccomp, cgroup hard ceiling, robust full descendant escape detection or
pre-exec resource enforcement. This tests bounded IO and process failure
handling only. The owner must authorize any later vendor backtests after the
entire engine passes engineering review. No original Gold data accessed.
