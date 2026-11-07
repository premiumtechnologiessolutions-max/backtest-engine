# FAC025 — Per-ounce canonical accounting precision guard (2026-10-29)

## Finding and fix

The research-only FAC025 closed-trade receipt adapter previously used a fixed **$0.0000001 whole-trade** absolute tolerance for independently recorded gross P/L, roundtrip fee and net P/L. A tiny positive position (for example **1e-9 oz**) has an expected fixed all-in roundtrip fee of only **$0.0000000004**. A missing fee, or even a 10-cent-per-ounce accounting distortion, could pass the old fixed-dollar tolerance.

`scripts/research_fac025_canonical_receipts.py` now reconciles **each** of gross, fee and net with an absolute tolerance of **$1e-8 per ounce × actual positive ounces**. Price-to-stop/target checks retain their separate price-unit tolerance. The canonical cost policy remains **exactly $0.40/oz ALL-IN roundtrip**; no fees were added, removed or reoptimized. The normalized daily-loss gate continues to recompute net from price, side, size and this frozen fee, rather than trusting the ledger's claimed net.

## Synthetic controls

`tests/test_fac025_per_ounce_accounting_precision.py` checks valid 1e-9/0.01/1/100 oz trades, a 0.10 USD/oz corruption independently in gross, fee and net, an entirely omitted tiny-size fee, and canceling opposite fee distortions. These are accounting regression fixtures, **not** executed Gold backtests. Source receipt provenance remains unauthenticated and the adapter is not a broker/tick simulator.

## Research and release boundaries

- **New historical backtests:** 0. **New monthly P/L:** 0. **New floating M1 drawdown:** N/A. **Approved strategies:** 0.
- No changes to frozen FAC025 grid, session/volatility filter, entry or exit hypothesis, shared capacity, or research registry counts. The 72 FAC025 configurations are still unexecuted correlated parameters of **one** hypothesis.
- Original private `Gold data.zip` and BID/ASK data are not part of this change and must never be pushed to the public repository.
- Before accepting results: pin and locally verify the original ZIP SHA, frozen plan and exact checkout, run actual canonical shared-capacity portfolio tests, independently reconcile trade/monthly/floating M1 evidence, and require embargoed prospective evaluation. Keep PR #1 **Draft/unmerged**.

This patch does not establish any 12/12 positive-month performance or live trading suitability.
