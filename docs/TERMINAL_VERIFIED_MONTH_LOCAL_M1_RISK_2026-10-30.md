# Both offline terminals: verified month-local M1 close-equity risk — 2026-10-30

Engineering-only, synthetic tests. The source-audited scorecard already supplies per-month `month_local_max_observed_m1_close_drawdown_usd_per_oz` and job `max_observed_m1_month_local_drawdown_usd_per_oz`. The terminals previously displayed only global-peak drawdown, without independently checking month-local fields.

This patch renders **global-peak and month-local observed M1 close-equity drawdown separately** in the standalone and unified bilingual offline Quant Terminals. The defensive verifier rejects incomplete pins, booleans, NaN, negatives, month-local values greater than global-peak DD, and job/month maxima disagreements. Missing independently pinned M1 equity evidence is **N/A**, not zero.

Month-local peaks reset at each UTC month, anchored to the last *observed* prior-month equity mark. This does not estimate intrabar losses, interpolate market gaps, certify BID/ASK fills, prove shared-capacity portfolio returns, or establish clean OOS. Fee remains exactly $0.40/oz ALL-IN roundtrip. Original private Gold ZIP is not published.

Synthetic tests: `pytest -q tests/test_research_batch_verified_monthly_terminal.py tests/test_research_terminal_verified_monthly_section.py`. No new source strategy backtests, source monthly net, worst-month result or approved strategy. Draft PR #1 must stay unmerged.
