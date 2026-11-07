# Frozen Research Job — path-ancestor provenance gate (2026-10-28)

The offline Research Jobs intake now rejects a **symlink at any component** of the frozen spec or registry path, including a symlink to another directory *inside* the checkout. A symlinked checkout root is also rejected. Previously, only the final file's symlink status and the resolved path's containment were checked, so a directory alias within the checkout could pass metadata fingerprinting. This change applies to both `frozen_request` and the `preflight_job` recheck through their shared source readers.

Four synthetic regression tests cover symlinked `docs/`, a nested spec parent, `research/`, and the checkout root. Existing safe ordinary files continue to be accepted. This is **not a race-free security sandbox** against concurrent hostile path replacement; any future worker still needs directory-FD-based source access and an isolated checkout.

**Research evidence:** This patch runs no original XAUUSD data, no canonical backtests and no forward months. Monthly P/L and observed M1 floating DD remain unchanged / N/A where unverified. Keep the repository's public branch free of raw BID/ASK, keep PR #1 Draft and do not enable live trading.
