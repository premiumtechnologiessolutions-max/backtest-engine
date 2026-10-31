# NRF-FAC-006 — original-source three-slot parity FAIL (2026-10-26)

**Status: BLOCKED; do not publish portfolio P/L as verified.** [Frozen FAC006 specification](FAC006_FROZEN_SHARED_CAPACITY_PORTFOLIO_2026-10-26.md) requires the unconstrained three-slot portfolio to reproduce three independent canonical `run_fast` ledgers before the one-slot joint results can be accepted.

The runner `scripts/run_fac006_shared_portfolio.py` and tests were added to GitHub. Synthetic CI passed **652/652** on commit `43ffd97e5a78b21fcb34b2eeb9f72c6e96a061e7`, [Actions #40389713190](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40389713190). The **exact CI-verified artifact** was then run locally on private original 2012 `Gold data.zip`, verified SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.

**Original 2012 parity FAILED as required:**
- Sum of three independent canonical `run_fast` references: **739 filled trades, $295.60 fees**.
- Three-slot shared portfolio: **737 filled trades, $294.80 fees**, with **zero capacity rejections**.
- Maximum absolute exit-booked monthly net difference **$26.40/oz**; maximum absolute observed M1 equity difference **$34.80/oz**.
- Component A_RANGE_SLOW matched 44/44 and component C_RSI_BASE matched 456/456.
- Component B_RANGE_FAST differed: canonical **239**, portfolio **237**. Original event-level investigation found canonical entries at **2012-01-18 10:16 UTC, 2012-02-02 15:16 UTC, and 2012-02-14 14:16 UTC** from signals confirmed one minute earlier, which the portfolio rejected because the same strategy occupied its slot at the confirmation M1 open. One additional portfolio entry at **2012-02-03 12:45 UTC** would not exist in the canonical reference because the canonical Feb-02 trade was still open.
- This is a **documented same-strategy pending-signal policy mismatch**, not missing source bars or a profitable trade discovery. `run_fast` retains a signal up to its one-minute expiry when the strategy's prior position closes on the confirmation bar; `run_portfolio` currently rejects the same signal immediately if the strategy was occupied at that minute's open.

**Safety outcome:** The runner intentionally raised `AssertionError` and wrote no successful `research_summary.json`. Do NOT count FAC006 as a completed original-source portfolio validation or use its P/L. **2013 original joint run was not attempted** because the 2012 acceptance gate failed.

**Next:** preserve the default conservative `run_portfolio` behavior for compatibility, but implement an explicit opt-in policy for deferring same-strategy Market signals until the next observed M1 open (maximum 60s) so a new, separately frozen engineering control can match canonical `run_fast`. Test both policies on synthetic collision cases and the original three-slot parity before reporting one-slot results. If no parity, keep blocked. No raw quotes uploaded to GitHub.
