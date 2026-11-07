# 2026-10-27 — Correcting double-counted inactive strategy specifications

## Finding
The registry arithmetic previously counted parameter specifications with **zero fills in both design years** as *active distinct specifications* whenever other specifications in the same family had filled trades. Those same 14,196 specifications were also counted in `zero_trade_parameter_specs_excluded`. This double-counted the active/excluded partition and inflated the reported distinct active specification count from **312,924** to **327,120**.

Affected families: FAC014 5,376; FAC016 500; FAC017 512; FAC018 7,808. Their total is 14,196.

## Correction and reconciled baseline
- Active distinct specifications: **312,924** (previously 327,120).
- Excluded zero-trade specifications: **39,896** (unchanged).
- Total unique design specifications including 100 one-year feasibility negative controls: **352,820**.
- Invariant: **312,924 + 39,896 = 352,820**.
- Active annual backtests: **614,956** (unchanged).
- Active exit-booked monthly P/L values: **7,379,472** (unchanged).
- Total annual executions including zero-trade controls: **705,540** (unchanged).
- No parameter configuration was profitable in all 24 exposed design months, as previously reported.

The audit now subtracts both-year-zero specs from the distinct active-spec count, counts them once as excluded, and rejects impossible counts exceeding the family's total specifications or zero-trade annual executions. Regression tests enforce the exact partition and reject malformed synthetic registry copies.

**Limits:** This corrects PUBLIC METADATA ARITHMETIC ONLY. No original Gold ZIP, broker quotes, trades, or independent forward/OOS samples were used or uploaded. It does not change execution logic, fees ($0.40/oz all-in), historical strategy results, or support any claim of future monthly profits. Keep PR #1 Draft/unmerged; current-head pytest and CI are not claimed by this document.
