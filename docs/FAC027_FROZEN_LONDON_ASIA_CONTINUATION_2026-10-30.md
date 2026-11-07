# FAC027 — frozen London-to-NY Asian-range continuation (2026-10-30)

**Status: PREREGISTERED / NO MARKET RESULTS VIEWED.** This is one logically distinct hypothesis with 16 correlated parameter configurations, not 16 independent discoveries. Historically exposed 2012/2013 only; not clean OOS.

## Fixed causal hypothesis
At 08:00 America/New_York on a weekday, use only actual observed M1 BID-reference candles from the completed same-day 00:00–03:00 NY Asian window (180 minutes) and 03:00–08:00 NY London window (300 minutes). Reject any missing, duplicated, non-minute-aligned, or nonconsecutive minute in the complete 480-minute context. Calculate Asian high/low and London open/close/high/low. Long only when London closes above Asia high by at least threshold × Asia range and London close > London open; short symmetrically below Asia low. Require abs(London close−London open)/(London high−London low) >= efficiency. Use median of the last five *completed* London H1 high-low ranges as a fixed preknown USD/oz risk unit; reject zero/nonfinite or unit / signal price >0.003. No intraday reoptimization.

## Frozen grid (16 correlated configurations)
- Asia breakout buffer fraction: 0.05 or 0.15.
- London directional efficiency: 0.30 or 0.50.
- Stop distance: 0.8 or 1.2 × frozen risk unit.
- Target distance: 1.0 or 1.5 × frozen risk unit.
- One trade per NY day per configuration, one position at a time per configuration. Shared-capacity portfolio is a **separate** required experiment; no summing standalones.
- 2012/2013 original SHA-verified M1 only for design screening.

## Fixed execution and evidence
- Decision at 08:00 NY, enter at the **observed 08:01 NY M1 open only** (within one minute); otherwise no fill, never fabricate a minute. BID-reference OHLC, no claimed broker BID/ASK fill certification.
- At each actual M1 bar from entry: stop-first when both stop/target touched; adverse open gap-through fills at observed open; favorable gap to TP is capped at TP. Exit at first observed M1 open at/after 11:00 NY; if no such open by 12:00 NY mark invalid and fail closed (do not invent a close).
- Exactly **$0.40/oz ALL-IN roundtrip**, charged once per completed trade, no added spread commission. Report BID/ASK execution limitation separately.
- Monthly realized P/L booked at UTC exit month, zero-trade months included; M1 observed equity/drawdown, worst month, sample size, and annual net. Never equate parameter counts with independent hypotheses.
- Audit immutable input SHA256 1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121. No raw quotes on public GitHub. Reproducibility, canonical parity and prospective OOS are separate gates.
- No live orders, no MT5 integration, no billing/privacy changes; PR #1 stays Draft.

## Predeclared rejection and anti-selection
No claim of edge from 2012/13, even with 24/24 positive months. Reject any execution ambiguity, source gap, monthly ledger inconsistency or insufficient sample; report all 16 results including losses. Do not tune this grid after opening results. Independent forward evaluation with embargo and multiple-testing controls required before any approval.
