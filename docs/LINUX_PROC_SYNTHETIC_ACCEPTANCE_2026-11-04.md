# Synthetic Linux /proc lifecycle acceptance checks — 2026-11-04

Added `tests/test_linux_proc_identity_synthetic.py` to cover the **actual
read-only inspector parser**, not only a fake inspector's return values.
Every process and boot ID in the tests exists exclusively as a temporary
synthetic text fixture. No OS process, worker, external research engine,
market data archive, backtest, replay or broker is accessed.

The tests require:
1. A live member of the original process group blocks an exit verdict
   after the leader has disappeared.
2. Zombie members are not treated as live processes.
3. A reused numeric PID/group with a live member blocks recovery.
4. A changed boot ID cannot be treated as successful worker exit.
5. Corrupt /proc status fails closed rather than granting a retry.
6. A zombie or non-group-leader cannot be captured as a worker identity.

**Acceptance boundary:** Passing these tests is necessary but insufficient.
The inspector still lacks kernel-enforced descendant containment (cgroups),
a hardened launcher, Windows Job Object parity, crash-injection with
real isolated workers, and independent runtime audit. Do not enable
automated recovery or research execution based on this suite.
