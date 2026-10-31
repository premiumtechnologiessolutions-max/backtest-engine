# FAC025 independent source BID-proxy ↔ canonical parity gate (2026-10-30)

**Status: implemented with synthetic regressions; original private 2012/2013 run NOT executed in this commit.** Do not upgrade FAC025's registry parity flag or its rejected historical outcome until the original private ZIP is verified and this gate completes.

`scripts/verify_fac025_source_proxy_parity.py` independently regenerates the **frozen** FAC025 candidate list, selects **one** shared-capacity position across the 72 correlated filters using the existing frozen priority, and submits only those preselected intents to the canonical `run` and `run_fast` BID-reference simulators. It compares the canonical/fast full trade ledgers and every observed M1 equity mark, and separately reconciles source-vs-canonical entry/exit time, side, price, gross, exactly $0.40/oz cost, net, month-booked P/L, and global M1 close-equity drawdown. It fails closed on mismatches. This is a **cross-engine fill-parity gate**, not an independent re-derivation of the entry signals or an authenticated broker BID/ASK fill test.

The SHA256 of the private ZIP is streamed and checked against `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` before reading any private rows. Only aggregate parity metrics may be written locally; no raw M1, quote receipts, trades, or private source file are published to GitHub. Explicitly keep output outside any public checkout.

Run with the local private file and an outside-repository output destination:

```bash
python scripts/verify_fac025_source_proxy_parity.py "/private/Gold data.zip" --years 2012 2013 --out "/private/fac025_parity_aggregate.json"
```

Run synthetic regression coverage without the private ZIP:

```bash
python -m pytest -q tests/test_verify_fac025_source_proxy_parity.py
```

**Known limitations:** 2012–2016 are historically exposed, not clean OOS. Source reference quotes are BID-only proxies, not independently authenticated executable BID/ASK fills. No new strategy parameter search, no prospective acceptance, no MT5, no live orders, no fee change, no raw quote publication. FAC025 remains **REJECTED** (6/24 positive months; -$234.60233/oz historical source proxy); this gate is a reproducibility check, not a reoptimization. PR #1 remains Draft.
