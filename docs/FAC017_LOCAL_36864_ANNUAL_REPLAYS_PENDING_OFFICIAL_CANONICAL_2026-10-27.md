# FAC017 — private-source local replay, official canonical parity pending (2026-10-27)

**Status: LOCALLY COMPLETED; FROZEN SCREEN REJECTED; NOT OFFICIALLY CANONICAL-VERIFIED.** This is a negative historical design result, **not** clean OOS or a live-trading claim. The original frozen hypothesis and grid were committed **before** these outcomes at `e88adcea2f00927e15d93e37d11e8f95e7680911`; no parameters were retuned.

## Provenance and exact counts

- Input: private local `Gold data.zip` from the user's ChatGPT Library, **SHA256** `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` verified locally; **never uploaded to GitHub**.
- Executed locally using a port of the existing GitHub `scripts/batch_two_bar_shock_reversal_grid.py` causal signal and H1 gate, prior published FAC012B normalized M1 replay, and FAC015 completed-H1 ratio. The port is **not** the official full GitHub checkout and does **not** establish official `run_fast` parity.
- **18,432 correlated parameter specifications x 2 exposed design years (2012/2013) = 36,864 completed local annual parameter replays**; 34,624 annual replays filled >=1 trade; 2,240 annual replays filled 0 trades. 442,368 exit-booked monthly values computed including zero-trade controls; **415,488 active-run monthly values**. Distinct pre-execution signal-rule combinations <=288, not 18,432 independent hypotheses.
- 2012: 18,432 executed, **16,896 active**, 1,536 zero-trade, 254 distinct realized signal streams, best 10/12 positive months.
- 2013: 18,432 executed, **17,728 active**, 704 zero-trade, 260 distinct realized signal streams, best 11/12 positive months.
- Combined: **maximum 20/24 positive months**, **0/18,432** 24/24; **0** passed the preregistered joint gate; **1,080** positive annual net in both design years (not an acceptance criterion by itself).

## Most-positive-months exploratory row (NOT a selected candidate)

`VSE17_N32_Q2.50_R0.55_ACTIVE_ALL_SL2.25_TP0.50`:
2012: 9/12 positive months, **-$4.74875/oz** after exactly $0.40/oz roundtrip, 22 fills, $8.80 total fees, worst month -$5.76625, annual floating M1 DD $11.13625.
2013: 11/12 positive months, **+$7.38875/oz**, 19 fills, $7.60 total fees, worst month $0.00 (no loss month, one flat month), annual floating M1 DD $6.66875.
Together **20/24**, **+$2.64/oz**, **41 trades**, **$16.40 fees**, worst month **-$5.76625**, max annual floating DD **$11.13625**. **REJECT**: far below preregistered >=100 fills *in each year*, and 2012 net negative. This is a multiple-tested exploratory maximum, not a prospectively validated strategy.

## Execution integrity and pending gates

- M1 observations only; no fabricated minutes, complete UTC-anchored M15/H1 candles only; prior-known H1 ratio; DST-aware local session conversion; <=60s next observed entry; stop-first, adverse stop gap-through; one position per annual replay; exactly $0.40/oz ALL-IN roundtrip, no second spread fee.
- All 36,864 annual rows reconciled against 12 exit-booked monthly P/L points and exactly $0.40 x filled trades. A separate slow M1 state-machine replay checked **8 fixed/exploratory annual samples**, **2,821,168 M1 equity marks**, and monthly/net/fees/floating DD with **0 numerical difference**. Slow checks share the signal generator and are **not** independent source validation.
- **Outstanding:** official repository checkout execution of the frozen FAC017 runner on this same SHA-verified archive, `run_fast` vs canonical full-trade and M1-equity parity, and confirmation of current-head GitHub Actions. No shared-capacity portfolio or prospective/OOS proof was run.
- **Registry totals remain unchanged pending official canonical verification.** Store this as a separate pending local experiment; do not add the 34,624 active runs to certified cumulative totals until verification.
- 2012–2016 were historically exposed; no new independent OOS. No raw M1 BID/ASK, original ZIP, detailed trade ledger, billing/privacy change, merge, or live trading.
