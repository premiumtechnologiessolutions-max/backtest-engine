# Discovery, shared portfolio and actual vendor execution increment

The existing local lab, same database, same authenticated server and same UI
now support synthetic_discovery and nautilus_synthetic jobs. Historical Gold
research remains disabled in this control surface.

## Advanced synthetic path

Generate four deterministic EMA/arithmetic specifications using existing Formula
grammar and mutation helpers. Evaluate each on two invented SIM instruments
through both canonical engines, requiring complete trade/equity parity.
Compute descriptive failure diagnostics and use ranked parent specs to propose
four distinct children. Evaluate generation two on the same fixture. Retain
lineage and source/ledger hashes for all 16 instrument/spec candidates.

Compile mean per-minute equity changes and covariance into a 16-variable QUBO.
Choose four candidates by QAOA and separately by exact classical objective.
Replay each selected set under shared capacity, per-symbol capacity and sticky
UTC daily realized-loss limits. Candidate admission priorities do not use future
P/L. Canonical intrabar closure labels are shifted to candle end for availability;
open-based exits retain their open timestamp. Coincident closures settle as a
batch before new entries. Output includes realized cash, fees and accepted /
rejected trades; compact JSON limits displayed rows and binds the full replay
with a digest.

Limitations: same-fixture adaptive/selection diagnostics are not unseen evidence.
Fixtures have invented cash-unit contracts and costs, not real symbol fee models.
The portfolio replays supplied candidate fills with admission gates; it does not
resimulate rejected paths, margin or intrabar floating equity. QUBO objective
and actual capacity-constrained realized portfolio result are distinct.

```console
norisk-lab discovery-demo --seed 0
```

## Real optional NautilusTrader runtime

```console
python -m pip install -e ".[nautilus]"
norisk-lab nautilus-demo --seed 7
```

Requires exact NautilusTrader 1.221.0 (Python 3.11..3.13). Its PyArrow >=21
requirement needs a separate environment from the legacy core CI constraint
PyArrow18.1. The optional CI job deliberately uses PyArrow21.0.0, Pandas2.2.3
and NumPy2.3.5. It creates an actual vendor BacktestEngine, native BID/ASK bars,
venue/account/instrument and a bounded strategy submitting/closing market orders.
The report contains native order/fill/position counts and native fill events.
The invented EUR/USD-shaped fixture is not historical EURUSD or broker data.
No user file, API connection, shell or broker is involved.

The vendor execution/cost model is separate from our canonical Gold model;
no cross-engine execution parity is asserted. The runtime is explicit opt-in,
not an autonomous worker. Missing or wrong dependencies fail without publishing
a successful result. Logs/UUIDs/wall time are excluded from deterministic digests.

LEAN, RD-Agent/TradingAgents runtime integration, FinRL, migration of historical
queues, GPU and original-source/OOS research remain unfinished. This increment
adds real operations to the runnable construction baseline, not final readiness.
