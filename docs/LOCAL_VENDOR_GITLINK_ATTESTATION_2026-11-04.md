# Read-only source attestation of vendored LEAN and Nautilus

`norisk_quant.vendor_checkout_attestation.attest_pinned_vendor_checkout`
now verifies *actual local bytes in a materialized Git submodule*, not
merely a caller-supplied vendor version field.

For each supported engine it checks:
- Host HEAD contains a gitlink at its fixed `vendor/upstream/...` path.
- Gitlink SHA equals the source pin required by the normalized trade adapter.
- Submodule checkout HEAD is exactly the same pinned SHA.
- The host and submodule Git worktrees are clean (including untracked files).
- Selected known vendor source entrypoints are non-symlink, tracked, bounded
  and SHA256 fingerprinted, without compiling or executing the vendor.
- HEAD identities are rechecked before the report is returned.

This verifier calls local Git read-only commands only, never downloads
source, imports vendor libraries, reads Gold archives or runs a backtest.

**Limits:** This is local checkout consistency, not independent remote
origin authentication or proof of execution; Git objects, the local machine
and recorded pins must still be trusted. The future isolated vendor
supervisor should capture this attestation before launching any executable.
The owner policy remains ENGINE CONSTRUCTION ONLY.

Synthetic tests construct a tiny private local Git repository and gitlink.
No real LEAN/Nautilus process is run.
