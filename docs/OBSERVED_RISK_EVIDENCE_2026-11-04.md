# Modeled portfolio risk evidence — engineering construction

The shared-capacity portfolio report now includes a **read-only observed
risk diagnostic** derived from its M1 equity timeline, in addition to
trade-cost and position reconciliation.

The diagnostic includes:
- Peak-to-trough observed modeled drawdown from the frozen zero-P/L base.
- Worst observed intraday drawdown, with UTC rollover carried only when
  the preceding minute is genuinely observed.
- Numbers of unobserved M1 timestamps between available marks; weekend
  and holiday closures are **not** automatically classified as corrupt.
- Optional strict frozen USD budget thresholds for independent callers.
- Explicit NO-BROKER-VALIDATION / NO-RESEARCH-ACCEPTANCE flags.

The calculation does not infer intraminute price paths, broker margin,
liquidation, commissions beyond the fixed research accounting contract,
historical macro data availability or actual fills. A passing result
is never a claim of strategy edge, OOS significance or safe live trading.
No real Gold ZIP or external engines were run in this construction change.

Paths: src/norisk_quant/observed_risk_evidence.py,
tests/test_observed_risk_evidence.py. Portfolio integration only enriches
summary reports and does not alter order creation or exit semantics.
