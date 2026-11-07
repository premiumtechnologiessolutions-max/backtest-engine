# BOS/Fibonacci Limit Engine — independent ledger parity audit (2026-10-25)

**Result:** 3,800 historical trades across **16 year × configuration scenarios** matched 13 execution fields in a local comparison.

Original XAUUSD M1 Gold data.zip, private outside repo, SHA-256: `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`.

## Verified local replay

| Year | H1 trend-only trades | H1 trend + minimum 5× cost trades | Both compared |
|---|---:|---:|---:|
| 2012 | 680 | 9 | 689 |
| 2013 | 704 | 27 | 731 |
| 2014 | 428 | 2 | 430 |
| 2015 | 405 | 1 | 406 |
| 2016 | 567 | 3 | 570 |
| 2017 | 278 | 1 | 279 |
| 2018 | 287 | 2 | 289 |
| 2019 | 405 | 1 | 406 |
| **Total** | **3,754** | **46** | **3,800** |

Comparator checks: `signal_at, entry_at, closed_at, side, entry_price, exit_price, stop, target, gross_pnl, cost, net_pnl, exit_reason, gap_minutes`. Time, side and reason exact; prices/PnL to ≤ 1e-7. The baseline per-year ledgers were produced by the **separate** standalone replay, so this is independent implementation comparison rather than self-comparison. All-in fixed fee $0.40/oz per roundtrip, no extra variable spread/commission. The experiment also exercised 30 deterministic randomized synthetic M1/Limit scenarios that reconcile equity, fee and causal timing; 8 BOS/H1 local generator tests and 6 separate portfolio tests passed.

**Critical scope:** for this local revalidation, parts of the GitHub modules were **reconstructed** in the offline execution environment; files were not all byte-identical with GitHub's current commit. The parity match is encouraging but is **NOT proof that the exact current GitHub repository package has passed a full test suite**. The GitHub repository now contains `scripts/verify_bos_h1_parity.py`, which imports the **actual checked-out package** and fails on *any* mismatched trade field, signal count, per-year net or source ZIP SHA. Run it in an authorized environment with the original raw ZIP and independently generated archived trade ledgers; neither belongs in the repo. This is the remaining production parity gate.

## Operational readiness

- GitHub Actions was manual-only while the account's 2,000min/0.5GB quota was exhausted; no CI pass has been observed.
- No real tick data/quote order or fill chronology can be recovered from M1 bars. Same-entry-minute target is deliberately deferred; SL is stop-first.
- The BOS+H1 filters **still failed monthly profit acceptance** (previous doc `BOS_FIB_H1_REGIME_REJECT_2012_2019_2026-10-25.md`); parity validates accounting, **not profitability**.
- The local research archive `NoRiskFX_Limit_Engine_3800_Trades_Parity_2026-10-25.zip` holds reproducible source files, audit JSON and Arabic report without raw licensed XAUUSD data.

## Actual repository parity command

```sh
python scripts/verify_bos_h1_parity.py \
  --gold-zip "/private/Gold data.zip" \
  --reference-root "/private/nrf_bos_h1_validation" \
  --years 2012 2013 2014 2015 2016 2017 2018 2019 \
  --out "reports/generated/h1_bos_repo_parity.json"
```

Never label the repository engine verified merely because this script is committed. It must **execute successfully at the current immutable commit** with the exact source data, full archived ledgers, and green pytest.
