# Long research/audit session: BOS/Fibonacci implementation safety — 2026-10-25

**Decision: the tested conservative BOS/Fib+H1 variant is rejected for trading and for monthly-income claims.** This session improved simulator controls; it did **not** produce a profitable strategy.

## What changed in the central GitHub code

1. **Opt-in H1 regime staleness guard:** `H1RegimeSettings.max_regime_age_minutes`; optional CLI `--bos-h1-max-age-minutes 120`. This blocks setups that would rely on last week's H1 EMA state after a gap, without backfilling unfinished H1 bars. The default remains `None` to preserve the archived 3,800-trade original baseline.
2. **Opt-in M1 dual-pivot exclusion:** `BosFibSettings.ignore_ambiguous_dual_pivots`; optional CLI `--bos-ignore-dual-pivots`. A 3-left/3-right M1 bar that qualifies simultaneously as confirmed pivot high and low is omitted as a pivot because we do not know its tick sequence. The old default stays `False` for historical parity, and a dual-pivot omission can alter future structure regimes and **increase** total BOS signal counts.
3. **Causal Signal timestamps:** `Signal` must be timezone-aware and nonmissing; tests reject naive and NaT timestamps. Market-entry fast simulator already uses nanosecond signal confirmation rather than rounding seconds.
4. **Canonical fee enforcement:** `norisk backtest` rejects ALL-IN rates other than **$0.40/oz full roundtrip** to prevent accidental zero-cost results being presented as official.
5. **Frozen repeatable annual-runner:** `scripts/run_bos_fib_frozen_sensitivity.py` uses *actual package* `load_market`, `bos_fib_limit_orders`, `filter_orders_h1`, `run_limits`, and `report`; checks the private Gold ZIP's SHA-256; emits annual trade ledgers + weekly/monthly/equity + summaries + exact loaded M1 Bid/Ask slice hash. It does **not** upload the raw market data.
6. Regression tests: `test_h1_regime_age_gate.py`, `test_signal_timezone_contract.py`, `test_bos_dual_pivot_policy.py`, `test_canonical_fixed_cost_cli.py`, `test_frozen_bos_sensitivity_contract.py`.

## Local tests performed

- **24/24 scoped local pytest tests passed** using a local snapshot of central BOS/H1/Limit/portfolio modules, with H1 and dual-pivot opt-ins applied for the new rules. Other GitHub modules were not present in this subset; this does **NOT** establish a whole-repository CI pass.
- The independent full-price source ZIP SHA-256 was verified locally as `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.
- Local 2012 real-data re-run for **689 trades** across the original two H1 variants matched 13 ledger fields against the previous archived reference, within 1e-7 for numeric values. A multi-year extension of the replay hit the execution timeout and should not be counted as an additional new completed audit; earlier independent saved audits reported 3,800 matched trades.
- 2017 M1: **879** baseline BOS orders, **370** passing original H1; optional 120-minute H1 freshness left **365** of those 370.
- Observed candles that qualify as **both** 3/3 high and low pivots in the same M1 candle: 2012 **539**, 2017 **565**, 2020 **677**, 2024 **398**. No tick chronology is inferred. In 2017, excluding dual pivots changed BOS order count **879→888**; H1 freshness plus dual-pivot option produced 369 H1-eligible signals. These changes are **new strategy definitions**, not retroactive edits to archived baseline results.

## Frozen sensitivity: M1 BOS/Fib with *both* optional safety filters

Exact common settings: 3-left/3-right confirmed pivot BOS, Fib0.618 retracement pending limit, swing-based SL plus $0.10, TP 1R, first two same-side regime BOS events, limit expiry120 elapsed minutes, H1 EMA50 slope vs five *completed* H1 bars with maximum 120-minute confirmed H1 age, exclude simultaneous pivot high/low, one active position, synthetic BID OHLC stop-first, defer unprovable same-entry M1 TP, gap carry and adverse stop fills, **ALL-IN $0.40 per oz per completed roundtrip**. 1 oz every trade. Years run **separately**, not as one continuous account; 2020–2026 were previously exposed in research.

| Calendar year | M1 candles | Eligible H1 setups | Completed trades | Positive months | Net P/L 1oz | Max observed minute-close drawdown |
|---|---:|---:|---:|---:|---:|---:|
| 2012 | 352,975 | 871 | 668 | 0/12 | **−$242.85** | $243.73 |
| 2017 | 352,785 | 369 | 282 | 0/12 | **−$129.69** | $131.02 |
| 2020 | 355,432 | 1,193 | 929 | 0/12 | **−$387.99** | $389.33 |
| 2024 | 355,893 | 1,305 | 997 | 0/12 | **−$465.70** | $467.82 |
| **Sum of four separate annual runs** | 1,417,085 | 3,868 | **2,876** | **0/48** | **−$1,226.23** | not a combined portfolio |

All four local monthly ledgers reconcile to annual closed-trade P/L and sampled final equity within 1e-7, and every completed 1oz trade charged exactly $0.40. End-of-year synthetic closures were 0 in these runs. These results came from the local scoped Limit package with the new option flags applied; the newly committed full GitHub annual runner still needs an independently successful full repository/CI replay, so do not describe these local results as a certified run of the latest immutable Github commit.

Local full reproducibility archive in the chat: `NoRiskFX_Quant_LongSession_Safety_Audit_2026-10-25.zip` includes scripts, relevant local code/testing snapshot, full annual trade ledgers and monthly CSVs. It contains **no original market archive**.

## Why the search stays open

The user's target of profitable trading **every month** is not proven; no future profit can be guaranteed. Multiple M1 BOS/Fib parameter families, H1 filters and cost thresholds were historically tested and failed. We should **not** keep retuning these same strategies against already-inspected years to force 48/48. The objective is a single reproducible central engine, source hashes, execution parity and risk-aware evaluation.

**Remaining production gates:** exact package pytest + full script run with private data, immutable commit and locked dependency versions, real tick-level Bid/Ask fills or clearly labeled OHLC synthetic quotes, complete gap handling, multi-strategy margin/exposure constraints, pre-registered genuine walk-forward experiment with prospective future holdout. Github-hosted Actions remained temporarily manual-only after the account used 100% of 2,000 monthly minutes and 0.5 GB artifact storage; reset stated for **November 1, 2026**, see Issue #2.
