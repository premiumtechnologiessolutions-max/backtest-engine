# Recomputed monthly downside and canonical cost guard — 2026-10-28

## Change
The offline source-verified Quant Terminal now independently recomputes the monthly downside summary from each already reconciled canonical UTC month ledger. The batch scorecard includes exact frozen inclusive evaluation start/end dates, so the renderer rejects missing or invented calendar months and distinguishes partial edge months from complete months. It verifies nonpositive-month counts, longest nonpositive-month streak, months with trades, zero-trade months, and worst **three consecutive complete UTC calendar months**. When fewer than three complete months exist, the rolling metric remains **N/A**.

Every monthly fee must equal exactly **$0.40/oz per executed roundtrip**, within the existing small accounting tolerance; zero observed M1 marks are not accepted. A job's hash-pinned observed M1 global-peak drawdown must match the **maximum** monthly global-peak drawdown, not merely any one month. The renderer refuses contradictory totals, partial-month metadata, and missing months before producing private HTML.

The navy/gold bilingual offline view displays the consecutive downside streak, worst three-month window, months with actual fills, and partial UTC edges. It remains a **read-only historical standalone report**, not a shared-capacity portfolio or independent prospective OOS result.

## Evidence and limits
Synthetic-only regressions cover mismatched cost, zero M1 marks, missing months, forged downside fields, incorrect global floating DD, three-month window, and partial calendar edges. No new Gold ZIP replay was executed. This does **not** certify that SHA256 pins were independently frozen: the existing source re-audit and external pin provenance are still required. No raw M1 BID/ASK or private ZIP is published. No billing, privacy, MT5, broker, or live trading changes. PR #1 remains Draft.

Run:
```sh
python -m pytest -q tests/test_research_batch_verified_monthly_terminal.py tests/test_research_batch_monthly_scorecard.py
```
