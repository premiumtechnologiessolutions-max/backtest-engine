# FAC018 posthoc signal-capacity impossibility audit — 2026-10-27

**Disposition: FAC018 remains REJECTED. This is NOT a new backtest, new strategy, or prospective OOS result.** The original hypothesis and grid were frozen at `dc7f3cac`; this audit does not change either.

## Why this matters

FAC018 preregistered **at least 100 actual filled trades in EACH of 2012 and 2013**. Every one of its **9,216 correlated parameter specifications** can generate **at most one fill per completed signal** in the frozen one-position execution model. Consequently, the count of causally generated signals is an upper bound on fills, independent of any stop/target choice or execution slippage.

The two original annual candidate exports, whose SHA256 checksums match the already-published FAC018 report, show:

| Metric | 2012 | 2013 |
| --- | ---: | ---: |
| Parameter specifications | 9,216 | 9,216 |
| Signal-rule groups before SL/TP sweep | 144 | 144 |
| Groups with any signals | 20 | 20 |
| **Largest signal count of any specification** | **39** | **29** |
| Largest actual filled-trade count | 39 | 28 |
| Preregistered required filled trades | **100** | **100** |

**Mathematical conclusion:** even under impossible perfect execution of every eligible signal, no FAC018 specification can reach the sample-size gate in either year: **39 < 100 and 29 < 100**. The family could have been rejected on this single pre-known gate before its 18,432 full M1 annual execution sweeps, *provided the causal signal counts were computed before looking at profitability*. This is a retrospective process improvement, not a claim that we actually preregistered or ran such a preflight before FAC018.

The original batch remains **2,560 active / 15,872 zero-trade annual executions**, maximum **17/24** positive months, **0** frozen joint passes, worst month of the exploratory 17/24 candidate **-$7.13/oz**, maximum observed annual floating drawdown **$25.54375/oz**. The full registry total stays **590,380 active annual backtests** and **7,084,560 active monthly P/L values**; **zero new replays** in this audit.

## Reproducible evidence and implementation

Private original `Gold data.zip` was retrieved locally and its SHA256 checked as `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. The already completed FAC018 export ZIP was used locally, with its two annual candidate CSVs matching the SHA256 checksums from the published report:

- 2012: `c2ace7a900e2584b1a32fe4176ed0f8256eb09198190220bef902a627883124d`
- 2013: `3d4bd29e2614cd34ca66fc54f87c1c7cf1564619d2f63bbe0a6288c8179e3db4`

`scripts/audit_signal_capacity.py` checks strict nonnegative integer signal/fill counts, at most one fill per signal, unique and matching frozen parameter IDs across years, and invariant signal counts within each pre-execution rule group regardless of stop/target. It rejects malformed evidence instead of certifying it. Synthetic regressions live in `tests/test_audit_signal_capacity.py`.

Run locally against the **private** existing exports (not on public CI):

```bash
python scripts/audit_signal_capacity.py \
  --year-csv 2012 /secure/FAC018/2012/all_candidates_monthly.csv \
  --year-csv 2013 /secure/FAC018/2013/all_candidates_monthly.csv \
  --rule-columns h4_window excursion retreat regime session \
  --min-fills 100
```

Expected status: `STRUCTURALLY_UNREACHABLE`. The public repository receives **only source, synthetic tests and this aggregate report**, not raw BID/ASK, M1 data, individual trades, or the full candidate exports.

## Forward protocol

For future frozen families with **one fill per generated signal**, first produce causal signal counts from already completed bars with fixed rules and **before** any risk-parameter profitability sweep. If the maximum per-spec signal count for even one required year is below the frozen minimum fills, stop that family as **structurally infeasible** and record the negative result; do not lower the fill threshold or retune the hypothesis after looking at outcomes. A sufficient count does **not** establish profitability, fillability, sample independence, or a pass. Shared-capacity portfolios require their own actual one-slot replay; component profits must not be added.

All 2012–2016 research remains historically exposed. This audit adds **zero** new monthly outcomes, **zero** new parity samples, and no clean OOS. Keep PR #1 Draft/unmerged. No live orders, billing/privacy changes, or market-data upload.
