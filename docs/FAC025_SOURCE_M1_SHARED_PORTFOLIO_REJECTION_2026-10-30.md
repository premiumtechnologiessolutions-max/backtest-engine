# FAC025 — original private Gold M1 one-slot BID-reference replay, 2012–2013 (2026-10-30)

**Result: REJECT as positive-every-month candidate. Source-file SHA verified locally; canonical `run`/`run_fast` trade-and-M1-equity parity is PENDING. Not broker-executable BID/ASK fills, not clean OOS, not approved.** Execution contract was [frozen before this result](FAC025_SOURCE_M1_ONE_SLOT_PREDECLARATION_2026-10-30.md), commit `a7bfdd826ec8a0348c04e513d0d44b6dacceff3c`.

## Reproducible scope
- Private archive SHA256 exactly `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`; **never uploaded**. Original observed UTC M1: **352,975 (2012)** and **352,317 (2013)**.
- Frozen FAC025-ENTRY-A M15 sweep/reclaim, two older completed H1 closes, normalized risk, NY DST sessions, completed contiguous volatility gate, realized same-day loss halt. **72 correlated frozen parameter settings = one hypothesis**, not 72 discoveries.
- Separate 72 one-slot standalone historical BID-proxy simulations, **plus one actual unified one-slot portfolio** using first eligible frozen ID priority and a common realized-loss ledger. Do not sum standalone results.
- Exact next observed BID open at decision+60s; no fabricated minutes, stop-first and adverse gap-through, end-of-year forced exit if needed, **$0.40/oz ALL-IN once per completed trade**. ASK observations validated but not charged again as a second spread. Research only; no authenticated quote receipt chronology.
- Code: `scripts/research_fac025_source_one_slot.py`; synthetic tests: `tests/test_research_fac025_source_one_slot.py`. Full local run repeated twice with identical aggregate JSON SHA256 `b9eb3fa3bf0319609c9b14f36274a9f0c79ce0901e06cc62123e0852989de02c`. This hash refers to a **private aggregate JSON** containing all 72 monthly series, not raw quotes.

## Unified shared-capacity one-slot portfolio — actual simulation, USD per 1 oz

| Metric | 2012 | 2013 | Combined note |
|---|---:|---:|---|
| Observed original M1 | 352,975 | 352,317 | 705,292 |
| Structural normalized-risk candidates | 1,620 | 1,428 | 3,048 |
| Exact eligible later M1 open present | 1,603 | 1,413 | 3,016 |
| Completed portfolio trades | 338 | 280 | **618** |
| All-in roundtrip fees | $135.20 | $112.00 | **$247.20** |
| Net P/L after all-in fees | **-$117.952194** | **-$116.650136** | **-$234.602330** |
| Positive observed UTC months | **4/12** | **2/12** | **6/24** |
| Worst realized month | Dec -$27.359518 | Jan -$24.653662 | **Dec 2012 -$27.359518** |
| Worst three consecutive months **within annual run** | Oct–Dec -$55.542596 (96 trades) | Jan–Mar -$64.297312 (96 trades) | No cross-year continuity claim |
| Max observed M1 **global-peak** close-equity drawdown | $124.391458 | $117.150136 | **Separate annual replays; not additive** |
| Max observed M1 **month-local** close-equity drawdown | $30.174518 | $27.023582 | Separate annual replays |
| Capacity-skipped candidates | 26 | 16 | 42 |
| Gate-blocked candidates | 1,239 | 1,117 | 2,356 |
| Forced end-of-year exits | 0 | 0 | 0 |

**Monthly exit-booked P/L and month-local observed M1 drawdown** (USD/oz; DD is not intrabar/tick worst excursion):

| UTC month | Trades | Net after fees | Month-local M1 DD |
|---|---:|---:|---:|
| 2012-01 | 21 | +1.599264 | 7.500000 |
| 2012-02 | 28 | +3.454628 | 19.460000 |
| 2012-03 | 36 | -24.693332 | 27.368666 |
| 2012-04 | 20 | -11.557326 | 17.462326 |
| 2012-05 | 32 | -16.264778 | 21.002974 |
| 2012-06 | 21 | -7.296678 | 14.236678 |
| 2012-07 | 24 | +5.858612 | 7.810000 |
| 2012-08 | 33 | -17.276288 | 17.526288 |
| 2012-09 | 27 | +3.766300 | 8.910880 |
| 2012-10 | 30 | -14.394552 | 20.249552 |
| 2012-11 | 39 | -13.788526 | 20.432302 |
| 2012-12 | 27 | -27.359518 | 30.174518 |
| 2013-01 | 31 | -24.653662 | 27.023582 |
| 2013-02 | 28 | -16.399424 | 19.264052 |
| 2013-03 | 37 | -23.244226 | 25.119226 |
| 2013-04 | 24 | -7.030018 | 12.065018 |
| 2013-05 | 12 | -12.343608 | 17.228608 |
| 2013-06 | 19 | +7.477564 | 4.367422 |
| 2013-07 | 22 | -11.691656 | 12.202264 |
| 2013-08 | 18 | +0.670526 | 8.263868 |
| 2013-09 | 18 | -0.286884 | 9.730000 |
| 2013-10 | 16 | -10.137382 | 10.137382 |
| 2013-11 | 27 | -5.944206 | 7.484206 |
| 2013-12 | 28 | -13.067160 | 13.067160 |

**Standalone frozen grid audit:** 72 parameter settings × 2 historically exposed annual replays = **144 provisional source BID-reference runs**, not 144 independent hypotheses or canonical-certified replays. Every one of the 72 settings had **negative combined net** (range -$198.056194 to -$129.610488); positive-month counts ranged **4/24 to 8/24**. No 24/24, no strategy approved. These provisional 144 annual runs must **not** be added to the canonical-certified historical factory totals until independent engine parity and provenance checks pass.

## Independent cross-checks and limitations
- Original-source structural preflight totals **exactly matched** the previously published independent 2012/2013 diagnostic: directional sweeps 1,812/1,700; normalized-risk passes 1,620/1,428; observed next opens 1,603/1,413. This checks the **signal construction**, not fills.
- Two complete local runs produced byte-identical JSON. Synthetic tests cover stop-first, adverse stop gap, forced close, $0.40 fee, preknown loss halt, shared capacity, and crossed BID/ASK validation. Per-run booked monthly totals and total fees reconcile exactly to trade ledgers.
- No source-receipt timestamp authentication, broker tick reconstruction, full-session calendar provenance, independent official `norisk_quant.execution.run`/`run_fast` parity, or prospective OOS. Month-local DD is only observed M1 close marks; intrabar worst excursion may be worse. 2012/2013 are **historically exposed**.
- The observed **6/24 positive months and negative net** decisively fail this frozen policy's monthly-stability objective under the declared research model. **Do not retune this failed frozen policy and rebrand it as clean OOS.**
- No live trading, raw BID/ASK publication, merge, or billing/privacy change. PR #1 must remain Draft.

**Next gate:** independent official canonical/fast trade and M1-equity parity on selected source years with immutable source manifest, then only genuinely prospective embargoed tests for future new hypotheses. Research terminal must label this provisional non-approved evidence and never claim executable fills.
