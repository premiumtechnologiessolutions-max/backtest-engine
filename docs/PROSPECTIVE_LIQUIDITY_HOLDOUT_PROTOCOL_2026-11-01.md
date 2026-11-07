# Prospective XAUUSD liquidity experiment — protocol frozen 2026-11-01

**Status: protocol only. Not a completed experiment, approved strategy, or proof of edge.** This document deliberately contains no fitted parameters or historical performance claims.

## Why a separate experiment
BOS/Fibonacci/H1 and quote-reopen gap variants have failed historical checks. Years already inspected, including 2012–2026, cannot be relabeled independent out-of-sample (OOS). No strategy is accepted for live trading based on the work below.

## Data split and provenance
1. Use historical data through 2026-10-31 **only for research/training**, with each source ZIP SHA256 and exact loaded BID/ASK M1 fingerprint recorded. Previously examined years are explicitly **exposed**.
2. A prospective OOS window starts **no earlier than 2026-11-02 00:00 UTC**. Its end date and minimum sample must be committed *before* its quotes are opened for evaluation. If no post-cutoff quotes are available, record **NOT RUN**, never substitute older exposed years.
3. Collect the actual broker's tick BID/ASK data when possible. If only OHLC is available, label fills synthetic; preserve stop-first ambiguity and gap adverse-open policies. Do not infer intrabar chronology from M1 bars.
4. Store private raw quotes, credentials and private ledgers outside this repository. Publish only non-sensitive hashes, code version, configuration and aggregate outcomes. No raw ZIP upload.

## Liquidity-sweep hypothesis and registration gate
A proposed *distinct* family is a prior-session extreme sweep followed by a confirmed reclaim, rather than BOS/Fib retracement or quote-reopen gaps. Before testing on prospective quotes, commit a machine-readable immutable experiment manifest specifying:
- exact session boundary/time zone, lookback window and high/low construction, including incomplete session and gap behavior;
- sweep threshold and reclaim confirmation (which completed bar confirms the signal);
- entry timing, order expiry, stop/target, max holding time, concurrency and end-of-window closures;
- all parameter values and their training-only selection method; no OOS optimization;
- source identity, engine commit SHA, dependencies, timezone, contract size and canonical **ALL-IN $0.40/oz** roundtrip cost;
- precise OOS start/end, minimum trades, minimum active months, maximum permitted drawdown, and one primary acceptance statistic;
- number of hypotheses/variants examined, multiple-testing correction, and rules for aborting a family.

**No manifest => no prospective performance claim.** The proposed sweep/reclaim family is a hypothesis, not a pre-registered strategy until every field above is frozen.

## Causal execution and audit
Signals may use only completed bars available by signal time; enter no earlier than the next executable quote. Check timestamps for UTC awareness, sorted uniqueness, and non-NaT. Use BID/ASK directionally where supported; otherwise explicitly declare synthetic BID-only limitations. Compare independent reference and optimized engines trade-by-trade for timestamp, side, entry, stop, target, exit, reason, cost and P/L. Reconcile trade totals to weekly, monthly and equity outputs. Fail closed on source mutation, missing months, partial output, hash mismatch, or unexplained parity drift.

## Multiple testing and reporting
Report **every** candidate and rejected variant, including zero-trade and failed jobs; never rank only survivors. Track family-wide trial counts, overlapping exposures, correlation and repeated peeking. Use a preselected family-wise adjustment or false-discovery control and report unadjusted and adjusted uncertainty. A good backtest, positive monthly count or adjusted p-value does not guarantee future profits.

Separate three gates: (1) software correctness, (2) historical model validation, (3) truly prospective OOS performance. CI pytest only addresses the first. Keep PR #1 Draft and trading disabled until independent evidence supports all release gates.

## Required final artifact
A signed/hashed immutable manifest, data fingerprints, engine/dependency SHAs, complete execution logs, per-trade ledger, all-month and all-week tables (including zero-trade periods), gross/fee/net reconciliation, drawdown, multiple-testing accounting, failure register and explicit **PASS / FAIL / INCONCLUSIVE / NOT RUN** decision. Do not present an unexecuted protocol as results.
