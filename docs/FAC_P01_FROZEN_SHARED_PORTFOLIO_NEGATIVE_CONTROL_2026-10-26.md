# NRF-FAC-P01 — preregistered shared-capacity portfolio negative control

**Frozen before original XAUUSD composite results** on 2026-10-26. This is a *negative-control illustration*, not a selected or optimized profitable portfolio. The constituent parameter choices below are arbitrary fixed values, **not selected from either family's prior winners**:

1. `donchian_close_M15_10_fixedSLTP`: M15 close-confirmed Donchian breakout, lookback **10**, stop **$5/oz**, target **$10/oz** (FAC001 native signal family).
2. `m15_wick_rejection_v1`: complete M15 wick-rejection, wick/body **1.50**, min candle range **$3.00/oz**, stop **$5/oz**, target **$10/oz** (FAC003 causal entry family).

Original `Gold data.zip` source SHA-256 `1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121`. Evaluate full **2012** and **2013** separately with identical frozen settings and a year-end close. One-ounce positions, **one shared position capacity** across both signals, **$0.40/oz full roundtrip ALL-IN**, next observed M1 open within one minute, stop-first ambiguity and adverse gap-through. No fabricated fills. At same confirmed timestamp, **wick signals first, Donchian second** (stable sort); this tie priority is frozen here. The common replay uses `run_fast` on merged signals. Run each constituent separately with `run_fast` too and report the naive arithmetic sum **only as a demonstrably invalid portfolio comparison**, never as a tradable result.

Report per-year 12 UTC months of settled net, trade count, fees, M1 floating max drawdown, and number of positive months for all three runs. No optimization or alternative priorities permitted under P01 ID. 2012–2013 are exposed historical years; not OOS. The goal is to demonstrate capacity interactions, **not** to rescue previously rejected families or certify profitability.
