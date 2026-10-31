# XAUUSD research engine — single-command acceptance gate (2026-10-26)

**Status: IMPLEMENTED, NOT EXECUTED ON THE CURRENT GITHUB COMMIT.** This is a test orchestration tool, not a passing certificate.

The `scripts/acceptance_gate.py` command refuses to report success unless the same checked-out Git commit passes all stages: Python 3.12 and the four pinned core packages; a clean tracked working tree; compilation of all Python modules; `pip check`; the **entire** `pytest` suite; CLI help smoke test; and replay of the independent archived trade ledger against the authorized original XAUUSD source with all 13 fields matched.

Run in an installed, pinned local checkout with separately authorized private data:

```bash
python -m pip install -c constraints-ci.txt -e ".[dev]"
python -m scripts.acceptance_gate --out /secure/reports/acceptance.json \
  --gold-zip "/secure/Gold data.zip" \
  --reference-root "/secure/nrf_bos_h1_validation" --years 2012
```

The original source ZIP must match SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. For the 2012 archived two-variant replay the acceptance script requires **689 trades and 13 matching fields per trade**, not just matching aggregate P/L.

The acceptance gate now checks **both tracked modifications and untracked files** using `git status --porcelain=v1 --untracked-files=all`. A clean `git diff HEAD` alone is insufficient because untracked Python modules may affect imports and tests. After successful historical parity it rechecks the Git HEAD and worktree; if either changed during the run, acceptance fails instead of certifying the original commit. Synthetic regression cases cover clean/dirty status, changed HEAD and files appearing after replay. **These newly committed tests have not yet been executed in the full repository suite.**

The JSON report records the actual Git SHA and stage outcomes, without embedding market candles. Return code `0` is `PASSED_RESEARCH_GATE_NOT_BROKER_CERTIFIED`; `1` is failed; `2` is blocked because private parity inputs are absent. A successful internal research gate does **not** certify broker execution, tick fills, independent OOS, or monthly profitability.

As of October 26, GitHub Actions remains manual-only because the account quota is exhausted until the indicated November 1 reset. The original private market archive and archived reference root are not available to this execution environment, so this gate has **not** been executed end-to-end. Draft PR #1 must remain unmerged until actual execution evidence exists.
