# Vendor source preflight bound to the frozen Quant campaign

New command:
`python -m scripts.quant_vendor_source_preflight --design /private/design.json --checkout /path/to/backtest-engine`

The tool recompiles the entire frozen sharded research campaign. It then
checks *every* declared external simulator checkout against both its fixed
upstream gitlink and the exact parent source commit captured in the
campaign. Any missing checkout, dirty worktree, wrong gitlink or
source-commit mismatch is BLOCKED.

The verifier is read-only. It only executes local Git identity queries;
it does not start LEAN, Nautilus, any research job, fetch quotes or
open the Gold archive. SOURCE_VERIFIED is **not** engineering acceptance,
independent runner attestation or proof of a trading edge.

To use the preflight later, first materialize the pinned Git submodules
through a separately reviewed source acquisition step. The owner freeze
continues to prohibit actual market research until the full engine is built.
