# Exact 13-field historical replay — matching-invalid-ledger invariant gate (2026-10-27)

## Failure mode

Comparing the 13 archived and current-engine fields is necessary but not sufficient: **two identically corrupted ledgers** can match every field, including timestamps, fees and net P/L. The previous strict comparator could therefore accept impossible chronology, a nonpositive quote, a fee changed on both sides, or a matching but arithmetically invalid net result. This is a verifier robustness gap, **not evidence of any such error in actual archived gold trades**.

## New independent checks

After strict type/schema checks and all 13 field comparisons, `scripts/verify_bos_h1_parity.py::exact_ledger_check` now checks **both** current and archived trade ledgers:

- Signal timestamp <= entry timestamp <= exit timestamp (same instant is permitted).
- Entry, exit, stop and target prices strictly positive.
- Fee exactly the frozen **USD 0.40 per ounce per round trip**, with absolute floating representation tolerance `1e-9`; no extra spread charge is invented.
- `net == gross - fee`, with absolute `1e-7` tolerance.

These invariants apply to all nonempty ledgers and do not modify execution or strategy code. The existing empty-ledger schema requirement and timestamp precision checks remain unchanged. Regression tests include six paired-invalid-ledger cases and a two-trade valid case.

## Acceptance boundaries

GitHub CI on the new code/test HEAD must be checked separately. Public synthetic CI **cannot** certify original Gold ZIP historical replay, historical fills or broker-tick fidelity. The prior source-data 2012 historical comparison and separately audited FAC012B 14-sample parity retain their previously documented, distinct scope; they are not newly rerun here.

No original raw BID/ASK quote data or independent archived ledgers were uploaded. No strategy retuning, new performance claims, prospective OOS certification, portfolio simulation, live-trading endorsement, or monthly-profit guarantee. PR #1 remains **Draft**, with a full original-archive 13-field replay still required for this changed verifier.
