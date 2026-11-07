# First FVG CE limit-order standalone gold-data check — 2024

**Status:** independent local standalone replay of the same documented
research specification; **NOT certified parity with the current GitHub
src/norisk_quant/fvg.py + limit_engine.py**. Draft PR and GitHub CI
are still failing before runner assignment.

Source: original user-provided XAUUSD Bid/Ask M1 Gold data.zip, SHA-256
1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121
(2024 JSON member SHA-256
78d02159d9eb41a4a6122eed42b696e3b9b93c159a68b312ee2bb854e749fd32).

## Fixed rules (not full ICT/SMC model)

- H1 fully observed candles only. Three **consecutive** completed candles,
  third low > first high for a bullish FVG or third high < first low for bearish.
- Gap size at least 0.50 dollars/oz. Limit entry at 50% of the gap (CE)
  **only after third H1 candle close**, stop $0.10 outside candle-one extreme,
  target 2R, order expiry after 20 elapsed UTC hours.
- M1 conservative simulation. First entry fill at limit even if the market
  offered a better price; if price opens beyond stop on entry, adverse open fill.
  SL first if both SL and TP are in the same M1 candle. Max one open position.
- Cost **ALL-IN fixed $0.40/oz per complete round-trip**, once only.
  All results below at 1 ounce. This is research-price BID reference, NOT
  verified broker fills nor observed tick path.

## 2024 observed (from standalone replay)

| Metric | Result |
|---|---:|
| 2024 M1 candles | 355,893 |
| H1 complete 3-bar FVG orders | 871 |
| Executed trades | 357 |
| Unfilled expired/discarded orders | 513 |
| Months with positive closed-trade P/L | **3/12** |
| Closed-trade net P/L at 1oz | **-$925.325** |
| Worst closed-trade month | **-$164.09** |
| Runtime including reading source | 1.92 sec |

Arithmetic audits in the standalone test:
- Every trade's fee exactly $0.40.
- No trade entry precedes its confirmed FVG signal.
- Gross/fee/net arithmetic reconciles with final equity.
- All 12 months appear in the monthly report; no selection of positive months.

## Scope limits

This is a **single preselected implementation**, not proof that all FVG
or ICT models fail. Does NOT include displacement filter, BOS/CHoCH, session
time, multi-timeframe confluence, or real Bid/Ask tick execution.
2024 has been examined in previous research and is not independent OOS.
No strategy has been declared production-ready.

Standalone run artifacts are stored in the user's conversation at
\`/mnt/data/nrf_fvg_validation\`, with validate script
\`verify_fvg_2024.py\`, trade ledger, weekly/monthly CSV, daily equity,
and summary.json. They are **not** GitHub execution outputs.

## Next gate

Run \`norisk backtest --strategy fvg --execution reference ...\` against
the identical original 2024 input when CI and the execution environment are
available; compare **each** order and filled trade (entry/exit time, price,
reason) with this standalone baseline. Any discrepancy is a regression to
diagnose, not an acceptable difference to round away.
