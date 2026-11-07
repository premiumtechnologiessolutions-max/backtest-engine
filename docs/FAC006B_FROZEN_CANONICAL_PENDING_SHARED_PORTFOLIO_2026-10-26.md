# NRF-FAC-006B — FROZEN engineering follow-up: canonical-compatible deferred same-strategy Market signal

**Freeze date:** 2026-10-26. **Purpose:** fix a reproducible execution-policy mismatch exposed by FAC006 on original 2012 quotes. FAC006 remains rejected; this is a **new, separately labeled** implementation and NOT independent out-of-sample evidence.

FAC006 2012 original three-slot control disagreed with canonical `run_fast`: 739 vs 737 filled trades, $26.40 maximum monthly P/L difference. Root cause: at a Market signal's confirmation minute, a same-strategy position can still occupy the slot, but exit during that minute; `run_fast` retains the confirmed signal for the next observed M1 open **if within 60 seconds**. Existing `run_portfolio` instead rejects it immediately. The original conservative behavior MUST remain the default for all existing callers.

**New explicit opt-in:** `PortfolioSettings.defer_same_strategy_market_signals=True` (default **False**). At each M1 open, when a fully confirmed Market signal's **own strategy** was occupied at the beginning of that M1 bar, hold it in a deterministic pending list until the **next eligible observed M1 open**, never past `max_entry_delay_minutes=1` (60 seconds). Process pending signals by `confirmed_at`, then strategy name, then input order, before newer signals. If the strategy remains occupied or the signal expires, reject/expire it; never fabricate an entry or use a same-minute exit to recycle capacity. **Other-strategy shared-capacity rejection remains immediate**, not deferred. No modification to limit-order execution or original `run_fast`.

**Frozen signals, unchanged from FAC006:**
- `A_RANGE_SLOW`: FAC005B EMA8/72, H1 range ratio >=1.00, SL6.50, TP1.00.
- `B_RANGE_FAST`: FAC005B EMA16/26, H1 range ratio >=0.80, SL8.00, TP10.00.
- `C_RSI_BASE`: FAC004 M15 Wilder RSI14, lower threshold30, SL4.00, TP4.00.

**Portfolio:** one shared slot, max total 1 ounce, each strategy 1 ounce, fixed $0.40/oz ALL-IN roundtrip, stop-first, adverse gaps, yearly reset. **Three-slot control** max 3 open and 3 ounces must reproduce **three independent canonical `run_fast`** outputs on the original same source: exact filled count, fees, 12 monthly exit-booked nets, and every observed M1 mark-to-market equity within 1e-7. Full `validate_portfolio` and weekly/monthly/trade/equity reports for both capacities. If original 2012 or 2013 fails parity, DO NOT claim portfolio success.

Source `Gold data.zip` SHA256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121` remains private, no raw BID/ASK upload to GitHub. Test synthetic collision with opt-in True vs default False, then full GitHub CI and exact verified-source offline original data. **Both years historically exposed, and two components selected from same years. No OOS or live-trading claim.**
