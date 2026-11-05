# Unified local construction lab — 2026-11-05

## Run

Windows + Python 3.12: double-click START_UNIFIED_LAB.bat. First setup installs
local project dependencies using the internet. No broker or background service
starts. Leave the console open and visit http://127.0.0.1:8766.

Other platforms:

```console
python -m pip install -e .
norisk-lab serve
```

Default SQLite location: ~/.noriskfx/lab.sqlite3. Override before the subcommand:
`norisk-lab --database ./lab.sqlite3 serve`.

## One connected workflow

Validated bounded job → immutable source/runtime identity → SQLite exclusive
claim and stage events → invented M1 OHLC → two EMA plus two arithmetic
variants through existing reference and fast engines → full ledger/equity
parity → per-minute marked-equity increment mean and covariance → risk-return
QUBO with fixed cardinality → CPU QAOA simulation → separately labelled exact
classical baseline → atomic SQLite result → Arabic RTL UI.

Only synthetic campaigns and explicit bounded binary problem jobs are allowed.
The same invented fixture supplies the selection objective; this is not OOS or
market evidence. Candidate curves are independent accounts, not a shared
portfolio. Gold research, arbitrary input paths, shell execution, brokers and
external engine processes cannot be submitted through this coordinator.

## CLI

```console
norisk-lab status
norisk-lab --database ./lab.sqlite3 synthetic-demo --seed 7
norisk-lab --database ./lab.sqlite3 work-once
norisk-lab --database ./lab.sqlite3 submit spec.json
```

Synthetic spec: `{"kind":"synthetic_campaign","seed":7,"bars":720}`.
Identical frozen input/code/runtime identities deduplicate, even after success;
choose an explicit different seed for a new fixture. work-once runs at most one
queued job, not a daemon. synthetic-demo leaves a new job queued when older
queued work exists; inspect its returned state rather than assuming completion.

Supplied binary problems use kind quantum_optimization and a problem object
matching BinaryProblem's upper-triangular coefficients (see LOCAL_QUANTUM_BUILD).
Interactive limits: 10 variables, 3 QAOA layers, 256 angle evaluations;
synthetic candles: 240..3000. Statevector/exact baseline costs grow exponentially.

Optional real PennyLane QNode adapter: `python -m pip install -e ".[quantum]"`,
then submit `backend: "pennylane"`. CPU devices are allowlisted; GPU is disabled.
Package presence is not proof a device initializes. This is a library adapter,
not a copy of PennyLane internals or a quantum speedup claim. The separate CI
backend test must pass before optional runtime verification is claimed.

## Recovery and security

Saved results/jobs survive restart. Abandoned RUNNING leases expire after 120s
and requeue when a later explicit worker claims. Stage progress renews leases;
no heartbeat runs inside an in-flight optimizer. Cancelled/stale workers cannot
publish. Cancellation is cooperative between stages and cannot interrupt a
NumPy/PennyLane kernel. Mid-stage optimizer state is not checkpointed.

Server binds only 127.0.0.1. State-changing requests require matching Host,
Origin and a per-process random token. JSON bodies are bounded and do not select
filesystem routes. SQLite is local single-host storage, not a distributed queue.
This queue is separate from legacy historical research queues; they are not
silently executed, migrated or marked complete.

## Verification and remaining scope

Local tests cover lease recovery/fencing, concurrent claims, HTTP security,
complete real HTTP-to-existing-engines-to-QAOA flow, independent dense circuit
and QUBO objective oracles, persistence and code drift. unified-lab.yml runs
full repository CI, a separate optional PennyLane test and Windows construction tests on the pushed head.
A pending CI run is not a pass. First-install Windows execution and browser
visual layout require observed verification on those environments.

Remaining platform integrations: actual LEAN/Nautilus runtimes, RD-Agent and
TradingAgents proposal workers, isolated FinRL, multi-asset shared portfolio,
GPU compatibility/execution, host service lifecycle and untouched OOS. This
build is a runnable construction baseline, not the complete final platform.
