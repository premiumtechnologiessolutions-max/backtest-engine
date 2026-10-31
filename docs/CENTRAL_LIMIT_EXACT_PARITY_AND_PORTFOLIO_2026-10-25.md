# No Risk FX — Exact central-engine parity + shared LIMIT portfolio (2026-10-25)

**Status: LOCAL PASSED for scoped tests; GitHub Actions CI NOT PASSED. Draft PR #1 remains unmerged.**

## 1. Exact GitHub BOS/Fibonacci + H1 replay versus independent archived standalone reference

The actual repository **blob-identical** modules were reconstructed locally and verified with Git's \`hash-object\`:

| Module | Git blob SHA |
|---|---|
| \`src/norisk_quant/model.py\` | \`ea84faf8d2fa1ecbede6af0b47785386e5743702\` |
| \`src/norisk_quant/bos_fib.py\` | \`f388e91fa873dd7d6983fa9001d534562975ad7f\` |
| \`src/norisk_quant/h1_regime.py\` | \`2d145262ab7f8b422434a7dae18c5a214358d33d\` |
| \`src/norisk_quant/limit_engine.py\` | \`22aa795dc45b2c53d9ff71efc9abacee1a957d19\` |

Original **private** \`Gold data.zip\` SHA-256: \`1163474d1419212f1ebd199fb77f8dd6b3029040488f0b7180218fd339159121\`. No raw quote data was committed.

**Result:** all **8 years 2012–2019**, both frozen variants per year (**16 scenarios**), matched **3,800 trades** across 13 fields against the **independently produced archived standalone** ledgers. Confirmed the per-year generated order count and net P/L as well.

| Frozen variant | 2012–2019 trades | Net USD / 1 oz |
|---|---:|---:|
| BOS/Fib + completed H1 EMA trend | 3,754 | -1,573.81622 |
| Same + target >= 5 × $0.40 cost | 46 | -30.72986 |
| **Combined field comparisons** | **3,800** | — |

The checked fields are confirmation, entry and exit times; side; entry, exit, stop and target prices; gross, fixed fee, net; exit reason; and gap minutes. Numeric tolerances were \`1e-7\` USD, timestamp seconds exact, and categorical values exact. Largest observed single-trade net delta was at floating-point roundoff (~\`4.44e-16\`).

**Interpretation:** This is meaningful parity evidence for the **exact GitHub core modules** (rather than the earlier reconstructed approximation). It **does not** rehabilitate either losing BOS/H1 hypothesis. The local environment used an equivalent \`execution.Result\` dataclass stub and directly decoded the private annual JSON instead of importing the entire repository package through its CLI. Therefore it is **not** proof of whole-repo installation, full test-suite CI, broker fills or independent OOS.

## 2. New shared-capacity multi-strategy LIMIT portfolio

New module: \`src/norisk_quant/portfolio_limits.py\`.

- Multiple independent named LIMIT strategies, a **single** M1 clock, shared maximum positions and ounces.
- Oldest eligible order priority by placement time, strategy, original input order.
- No entry before placement, expired orders never resurrect; no same-minute reuse of freed capacity.
- Missing M1 minutes are **carried**, never force-closed solely for a gap. An adverse opening gap can stop worse than the intended stop level.
- If entry and stop occur within one observed M1 bar, stop-first. If only the target is touched on the entry bar, **defer** the unknowable target fill.
- Fixed **ALL-IN $0.40 per ounce per roundtrip**, once; no additional variable spread/slippage/commission.
- Shared realized and floating equity, observed open ounces, weekly/monthly reports, and an explicit count of deferred same-entry-bar TP events.

**Local tests:** **9/9 passed** on exact blob-identical GitHub modules for \`model.py\`, \`limit_engine.py\`, \`portfolio.py\`, \`portfolio_limits.py\`, and \`tests/test_portfolio_limits.py\`; the small \`execution.Result\` stub is structurally equivalent. Tests cover fees, shared capacity, gap-through, same-entry-bar target ambiguity, no-lookahead subminute confirmation, expiry, randomized streams, independent reference replay, and report exports.

**Real 2024 quote fixture parity:** using original 2024 BID M1, **10 predeclared windows × 300 observed bars**; **19 trade rows** matched independent single-strategy \`run_limits\` outputs, and the maximum difference in shared vs summed independent M1 equity was **$0.00**. These are **synthetic fixture orders**, not a new trading strategy or performance backtest. The source year contains 355,893 M1 rows; only 3,000 observed rows were used in this new parity fixture.

Reproducer: \`scripts/verify_portfolio_limit_2024.py --gold-zip "/private/Gold data.zip" --out "/private/reports/portfolio_limit_parity.json"\`. No private ZIP is included in the repository. A local audit JSON and code-only ZIP are kept with the conversation checkpoint.

## 3. Release gates still open

1. GitHub Actions quota exhausted for October 2026 (Issue #2); **no green CI claim** and **no merge to main**.
2. Run \`pytest\` against an actual full GitHub checkout when runner capacity returns, then re-run the archived parity tool with its actual importer.
3. Test true shared execution for market + LIMIT strategies, broker constraints and exposure if broker-level fidelity is later desired. Current M1 OHLC **cannot** reconstruct a tick path.
4. Any new liquidity/microstructure strategy must be preregistered, designed only on 2012–2016, validated on 2017–2019, and treated as **historically exposed** on 2020–Sep 2026; no guarantee of positive months.

**Decision:** keep rejected BOS/H1 variants rejected; advance central engine readiness without falsely promising profitability.
