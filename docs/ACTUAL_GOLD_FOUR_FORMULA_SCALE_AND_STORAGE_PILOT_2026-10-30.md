# XAUUSD arithmetic research: 4-formula original-source scale pilot (2026-10-30)

## Execution receipts (private, observed, TRAINING ONLY)

Authorized local original `Gold data.zip` SHA256:
`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`

On the same existing **exposed** training universe (2012, 2013), a single
arithmetic generation was expanded from **1** to **4** new formula proposals.
`scripts.run_arithmetic_research_cycles` completed with 4 annual replay
shards (2 formula/year blocks per training year), 8 formula-year tests,
**16 canonical Reference/Fast executions**, independently reconciled
monthly/weekly, transaction-fee, observed M1 equity and trade results.
A valid immutable next generation input was produced; SHA256:

`576b75d72ea5462524700e64ac31992cb628bf50992218d0ed44b0ac11680418`

The active accumulated historical memory expanded to **20 candidates**,
20 identities. The generation's local evidence files remained **outside
the PUBLIC GitHub repository**.

| New proposal | Completed trades | Combined net USD/oz | Positive months | 2012 net | 2013 net |
|---|---:|---:|---:|---:|---:|
| 1 | 1041 | +83.56 | 14/24 | -19.12 | +102.68 |
| 2 | 0 | 0.00 | 0/24 | 0.00 | 0.00 |
| 3 | 37 | -371.86 | 9/24 | -1.79 | -370.07 |
| 4 | 550 | -308.29 | 10/24 | -169.96 | -138.33 |

All numbers include the frozen **$0.40/oz all-in research cost** and
are separate hypothetical strategy outcomes, not a live/combined portfolio.
All four fail the *training* research screen. Even the net-positive first
formula has only 14/24 profitable months, below the 60% threshold.

**Performance:** From the initial generation file to final frozen feedback
file, elapsed time was **3.67 minutes** on the current local runtime.
Total generated data **456.95 MiB**, of which **455.42 MiB** is in
`equity_m1.csv` reports. These observations reveal an immediate storage
constraint: copying this workflow to thousands of formulas without
compaction is not production-ready and would likely require substantial
storage. No hardware-general throughput extrapolation is certified.

## Failure-conditioned hypothesis analysis

New `src/norisk_quant/research_failure_hypotheses.py` compares only
**fully reconciled formulas differing in exactly one field**. The
20-candidate train input yielded **14 such one-field pairs**, including
6 comparisons flagged for **preregistered retesting** under the
exploratory consistency rule. These are **post-hoc** comparisons chosen
on exposed historical training: direction, correlation and training
score are NOT a causal market mechanism, significance test or forward
trading edge. All results remain explicitly `NOT OOS`.

Both `scripts.research_training_dashboard` and the loopback-only
`scripts.research_local_monitor` now show research parameter contrasts
alongside strategy performance and caveats.

## Reversible cold-storage path

New `scripts/research_equity_cold_storage.py` provides deterministic
gzip compression of already feedback-verified M1 equity reports, with
uncompressed SHA256/byte counts, compressed SHA256, an immutable
generation manifest, full decompression verification, and a restored
report workflow. **Default archive mode does not delete original files**.
Pruning raw copies is explicit opt-in and is permitted only after
all compression files have been verified. Cached annual re-audit
can restore cold reports, run the full verifier, then return to compact
storage *only after successful acceptance*; failure leaves raw
forensic evidence intact.

A local pilot on one **35.31 MB** M1 equity report yielded **5.36 MB**
in gzip level 1. The pilot is suggestive, not a confirmed whole-campaign
compression ratio, nor an operational 1000-candidate capacity test.
GitHub synthetic regression tests cover archive/recovery/tamper cases.

## Provenance / acceptance limitations

- The 4-formula historical benchmark ran from the archived earlier
  verified source checkout, where core arithmetic engine/evolution and
  original Gold data input match the repository's known frozen baseline;
  **not** a fresh full newest-branch source execution.
- No newly untouched prospective data, real broker BID/ASK ticks,
  slippage/latency, margin model, or independently validated profitable
  strategy; do not deploy live trading.
- The code remains `feat/quant-engine-foundation`, **Draft PR #1**.
  No raw Gold ZIP, private trades, equity files, or broker data have
  been committed, uploaded or exposed to the public repo.
- Actual 24/7 worker deployment, resource-robust multi-thousand backtest
  acceptance, autonomous scientific research selection and prospective
  OOS results remain OPEN launch gates.
