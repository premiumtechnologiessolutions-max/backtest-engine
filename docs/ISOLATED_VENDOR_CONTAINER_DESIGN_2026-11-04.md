# Future isolated LEAN/Nautilus launch compiler (NOT executed)

Module: `norisk_quant.vendor_container_design`.

Compiles one locked-down Docker CLI argv vector from an exact source
checkout verified against the pinned Git submodule; requires a digest-pinned
vendor image and a frozen request SHA. The source and synthetic data mounts
are read-only, output uses a separate writable mount, Docker networking is
disabled, filesystem read-only, all Linux capabilities dropped, no new
privileges allowed, and explicit CPU/RAM/PID ceilings requested. Image
pulling is disabled. Credentials and arbitrary shell commands have no
fields in the input contract.

**This is a real command compiler, not a tested container sandbox.** Docker
is NEVER invoked by the function or its unit tests. The image must be
built and installed separately; the preconfigured entrypoint must exist
inside it, and the external supervisor must apply a wall timeout and
verify exit identity. Cgroup/seccomp/network/mount enforcement must
be independently observed before treating this as a secure vendor runner.
Actual LEAN/Nautilus execution remains blocked by the owner's
ENGINE CONSTRUCTION ONLY policy.

The output contains the command argv, including local mount paths; handle
it as private operational metadata, not a public shareable artifact.
