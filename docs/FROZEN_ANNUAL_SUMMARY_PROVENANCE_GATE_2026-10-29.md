# Frozen annual headline and provenance integrity gate — 2026-10-29

## Scope
The official `scripts/run_bos_fib_frozen_sensitivity.py` now independently verifies the annual `summary.json` before including its headline figures in the multi-year roll-up and before the evidence manifest is published. The runner compares the **persisted JSON** with the returned report object and checks:

- `trades`, `wins`, `positive_months`, `nonpositive_months`, twelve observed months, and zero missing observed months against executed trades and persisted monthly P/L;
- net P/L, actual fees and exact fixed `$0.40/oz` cost against executed trade records;
- source archive SHA256, loaded BID/ASK M1 fingerprint and M1 row count against the actual run inputs;
- frozen strategy ID, selected calendar year, fixed cost and explicit `do_not_claim_clean_oos=True` disclaimer.

This closes an evidence gap: SHA256 of an exported report proves that the file did not change after inventory creation, **not** that its headline numbers or source attribution were accurate when written. All existing trade-level, source-bar, gap, UTC-period and inventory audits remain in place.

## Validation
- 22/22 synthetic unit cases passed locally on the isolated new helper (Python, pandas and pytest available). They include fabricated winning-month counts, trade/win counts, fee and P/L totals, false source fingerprints, invalid OOS flags, nonfinite monthly values and negative trade costs.
- New helper and tests committed to the feature branch and wired into the official annual runner.
- **Not yet certified:** full GitHub repository pytest/CI on the new HEAD, original private Gold ZIP replay, 13-field historical parity, and genuine independent OOS. No historical result is changed or newly claimed.

## Safety and research limits
The repository visibility must be checked separately; GitHub previously reported it as **public**, not private. No original raw Gold ZIP or quote/trade dataset was uploaded. Keep PR #1 Draft. The 2012/2017/2020/2024 BOS/H1 historical screen remains rejected (2,876 trades, 0/48 positive months, -$1,226.23/oz across separate previously exposed annual runs). This gate is not broker execution certification, tick replay, or a profitability claim.
