# FAC025 original-source BID-reference canonical parity — VERIFIED 2012/2013 (2026-10-30)

**Outcome: execution parity PASS, strategy REJECT.** This is a reproducibility result on historically exposed 2012/2013 BID-reference data, **not** an authenticated executable BID/ASK fill test, clean OOS, or a trading approval.

## Evidence and scope

- Original private Gold ZIP SHA256 verified locally before reading: `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Raw BID/ASK quotes were never committed or uploaded to public GitHub.
- Exact public code snapshot: `d5ac3e059b90b6e4c39a9f0ca2cc56a4fbac7c94`; implementation `scripts/verify_fac025_source_proxy_parity.py`; synthetic regressions `tests/test_verify_fac025_source_proxy_parity.py` (**13/13 local pass**). [Full CI 40997162177](https://github.com/premiumtechnologiessolutions-max/backtest-engine/actions/runs/40997162177) **2902/2902 pass, one warning** on this code commit.
- Independently regenerated the original frozen FAC025-ENTRY-A candidates from original source, selected the one-position portfolio with frozen lowest-ID priority and a shared realized-loss halt. Submitted **only selected trades' frozen intents** to official `norisk_quant.execution.run` and `run_fast`. Compared both complete 15-field trade ledgers, every observed M1 close-equity mark, and source-vs-canonical fill times, sides, prices, gross, exactly $0.40/oz cost, net, monthly booked P/L, and M1 equity drawdown. **All comparisons passed** within declared absolute tolerance 1e-7.
- Two complete private local parity runs produced byte-identical aggregate JSON SHA256: `6485e7a430cf4f3cc94516e45051924305ee5f2a292efd14506d1ca78c20328c`. Only this aggregate fingerprint and the non-raw results below are published.
- This is **execution replay parity conditional on the frozen selected source signals**, not an independent re-derivation of signal logic or proof of quote receipt timestamps. Original FAC025 rejection and 24-month table: [FAC025 source one-slot rejection](FAC025_SOURCE_M1_SHARED_PORTFOLIO_REJECTION_2026-10-30.md).

## Source vs canonical vs fast — exact historical one-slot portfolio

| Verified item | 2012 | 2013 | Combined |
|---|---:|---:|---:|
| Original observed M1 close-equity marks compared | 352,975 | 352,317 | **705,292** |
| Completed selected trades compared | 338 | 280 | **618** |
| Positive observed months | 4/12 | 2/12 | **6/24** |
| Net after fixed $0.40/oz ALL-IN roundtrip | **-$117.952194** | **-$116.650136** | **-$234.602330** |
| Fees | $135.20 | $112.00 | **$247.20** |
| Worst month | Dec 2012: -$27.359518 | Jan 2013: -$24.653662 | **Dec 2012: -$27.359518** |
| Max global-peak observed M1 close-equity drawdown | $124.391458 | $117.150136 | **Separate annual resets; do not sum** |
| Source/canonical full trade and M1 equity parity | PASS | PASS | PASS |
| Canonical run/run_fast full trade and M1 equity parity | PASS | PASS | PASS |

The 72 filter configurations are **correlated parameterizations of one hypothesis**. The 144 provisional standalone annual runs are not added to canonical-certified factory totals, and the 72 standalone P/L streams are **not** summed as a portfolio. There is **no change** to the original FAC025 rejection, no parameter retuning, and **zero approved strategies**.

## Strict remaining gates

This comparison used BID-only reference execution and a fixed all-in fee, not independently authenticated BID/ASK broker fills or tick receipts. Source confirmation latency, session provenance, tick/intrabar worst drawdown, and clean prospective embargoed OOS remain unverified. The M1 close-equity DD is **not** a worst-tick/intrabar DD. No MT5 live connection, order placement, billing/privacy change, or PR merge. Keep PR #1 Draft.
