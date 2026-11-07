# Unified Market + Limit local acceptance — 2026-10-25

**Execution acceptance passed locally; no profitable strategy or broker execution is certified.**
Final package code checkpoint: `0d057c0f549f0afc7c6cabf2f1ff909c81eeb0f7` on
`feat/quant-engine-foundation`. Draft PR #1 remains unmerged. No historical
BOS/Fib/H1 research was replayed in this session.

## Implementation

- Market and Limit instructions share strategy allocations, position slots,
  ounce limits, and one realized/floating ledger. Opening instructions compete
  before later intrabar Limit touches, so a later low/high cannot retrospectively
  displace an opening Market instruction. Capacity consumed at the start or
  during an M1 stays reserved until the next observed bar.
- Exactly **$0.40/oz ALL-IN per roundtrip**, once. Floating equity reserves the
  same full fee; closing transfers it into realized P/L without charging twice.
  No variable spread, commission or slippage is added.
- Stops take precedence under M1 ambiguity; adverse reopening stops use the
  first observed open; positions carry through gaps. Limit entry-bar targets
  remain deferred. No inferred tick sequence or favorable gap fill is awarded.
- Optional elapsed-minute exits execute at an observed open, after already
  breached opening stops/targets and before that bar's later range. Reference
  and fast Market engines support the same option for QS01.
- Stronger portfolio audit checks every trade's side, prices, bracket, quantity,
  fee, gross/net P/L, exit reason/price, time eligibility, observed timestamps,
  per-strategy overlap, exposure chronology, realized chronology and terminal
  flatness. Separate source-price replay checks every floating mark.
- Whole missing weeks/months retain unknown marks and allocated equity changes.
  Resumption differences spanning unobserved periods are separately labeled.

## Independent package and full-suite verification

Windows, Python **3.12.14**, pandas **2.2.3**, NumPy **2.3.5**, PyArrow **18.1.0**,
pytest **8.4.2**. Exact versions and module/package hashes are in
`audits/local-package-verification-2026-10-25.json`.

| Gate | Result |
|---|---|
| Full repository source suite | 263 passed, 0 failed/skipped |
| Full suite using installed wheel core outside repository directory | 263 passed, 0 failed/skipped |
| Extracted source-distribution tests/scripts plus installed wheel core | 263 passed, 0 failed/skipped |
| Build source distribution and wheel | Passed |
| All 23 installed core modules vs repository and built wheel | All identical |
| Dependency consistency (`pip check`) | No broken requirements |
| Installed CLI help: root, backtest, audit-gaps | Passed |

These are three executions of the **same 263 tests**, not 789 unique tests.
Seven existing pandas regex capture-group warnings in `ticks.py` remain;
they do not fail tests. This Windows/Python 3.12 evidence does not assert that
the GitHub Linux/Python 3.11 matrix ran.

The first source archive omitted research helper scripts needed by two test
modules. `MANIFEST.in` now includes scripts and documentation; the extracted
archive test run passed without adding the repository to its import path.
Wheel-core imports were confirmed from `site-packages`, rather than `src/`.
The declared pandas minimum is corrected to **2.2**, matching the `ME`
resampling alias used by the reports; 2.1 must not be advertised as supported.
The final wheel metadata and dependency consistency were checked after rebuilding.

Installed wheel SHA-256:
`d9dc988d59c26b65ebea957871bdad6c356e3d353c87609555b994b648f80d0d`.
Every core module byte was independently compared between repository,
installed wheel and built wheel; archive identity is recorded separately.

Concurrent branch changes were preserved through two development-branch merges.
The public QS01 CLI/API delegates to the already audited generator rather than
maintaining a second rule implementation. The alternate holding-option spelling
is a validated constructor alias; the original positional Settings contract is
preserved. The exact-ZIP design runner and actual-observation month counts were
retained, and both design runners now fail closed on a missing calendar month.
No QS01 historical execution was repeated during this integration.

## New real-M1 acceptance gate

Command: `python scripts/verify_unified_real_m1.py --json /private/2024.json --out /private/acceptance`.
The installed wheel at clean checkpoint
`069d58fe6556a74d55840fcd8484561b09d22274` was used. Runtime: **83.026 seconds**.

Input: **355,893** original local Bid/Ask M1 rows, from 2024-01-01 23:00 UTC
through 2024-12-31 21:58 UTC. No duplicate timestamps or Bid/Ask OHLC anomalies
were found. There are 306 non-60-second intervals; missing intervals include
ordinary trading closures and are not automatically classified as corrupt.
The actual annual frame also passed an on-disk Parquet write/read equality gate.

- Annual JSON SHA-256: `78d02159d9eb41a4a6122eed42b696e3b9b93c159a68b312ee2bb854e749fd32`.
- Loaded M1 Bid/Ask SHA-256: `7cf1d13a63cb6fb1a986e8d921db27c9abf936e63e62d9b8f270efb027c4c45c`.
- Original source ZIP was unavailable locally; its preregistered byte identity
  was **not verified**. Extracted-file hashes do not establish that identity.

| Check | Result |
|---|---|
| Donchian reference vs fast | 606 signals; 171 trades; every ledger field, all 355,893 equity samples and signal counters match |
| Mixed execution fixtures vs independent single engines | 682 trades: 355 Market + 327 Limit; all ledger fields and minute equity match |
| Fractional allocations | 0.5 oz Market + 1.25 oz Limit; max observed 2 positions / 1.75 oz |
| Mixed completed-roundtrip fee total | $234.50; per-trade fee and gross-minus-fee reconciliation passed |
| Independent source-close replay | Every position's floating P/L, open count and ounces match each observed M1 |
| Weekly/monthly realized and equity totals | 53 weeks / 12 months reconcile |
| Constrained replay | Max 1 position / 1.25 oz; 397 trades; 285 capacity rejections; source-price floating replay passed |
| Limit entry-bar target deferrals | 9 explicitly recorded |

The fixture schedule is fixed and generated from already completed M1 closes.
It is an execution diagnostic, not a trading strategy. Its net was **-$210.7675**
in the unconstrained run and **-$100.855** with constrained capacity. Donchian's
171 trades include one synthetic end-of-data close; its result is used only for
kernel parity, with no profitability selection or acceptance claim.

Full aggregate evidence: `audits/unified-real-m1-2024-2026-10-25.json`.
Its `code_tree_dirty: false` confirms a clean execution checkpoint. Subsequent
integration only added reporting/source-coverage compatibility. AST comparisons
in the final package manifest prove the Market, fast, Limit, unified portfolio
and QS01 signal functions unchanged from that real-data gate. Final source and
installed-wheel byte identity is recorded separately at `0d057c0`.

## Remaining boundaries

Synthetic common BID OHLC reference prices cannot validate broker Bid/Ask fills,
tick paths, slippage or margin. Limit expiry is inclusive at observed minute
openings; an expiry versus a later touch within the same minute is not resolved.
Open marks inside missing intervals and exact intra-minute drawdowns remain
unobservable. The generic portfolio validator does not independently validate
floating prices without source closes; the new real-data gate supplies those
closes and performs that separate check.

GitHub Actions remains manual-only under the recorded account quota blocker;
**no GitHub CI success is claimed**. No raw market data or detailed quote/trade
ledgers were committed. No live trading, merge or monthly-profit guarantee.
