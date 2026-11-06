# Unified local lab

Install the project with Python 3.12 and open the dashboard at
http://127.0.0.1:8766 after running `norisk-lab serve`. On Windows,
`START_UNIFIED_LAB.bat` installs into `.venv-lab` and starts the server.
Install optional dependencies in the same Python environment.

```console
norisk-lab discovery-demo --seed 7
norisk-lab work
norisk-lab status
```

The foreground worker processes runnable jobs from the same SQLite database as
the dashboard. A job keeps a fenced lease during execution. An interrupted
attempt can be reclaimed after lease expiry and rerun from its immutable
specification. Starting a job from the dashboard targets that job explicitly.
The portfolio records observed M1 floating equity, per-instrument contract
multipliers, initial and maintenance margin, sticky daily equity loss limits,
and closures at fresh observed marks when maintenance margin is breached.
The discovery path replays planned entries and exits under those gates. It uses
invented prices and contract terms. After both selections are frozen, the lab
checks reference/fast parity and replays both portfolios on separately seeded
invented bars from a later, disjoint time window. The receipt binds the frozen
candidate specifications, both selection lists and the validation fixture
digests. This validates the separation in the software pipeline only.

## Quantum backends

NumPy is the default CPU backend. Install `.[quantum]` for PennyLane and
Lightning on CPU. Install `.[gpu]` and the device manufacturer's OpenCL driver
for `norisk-lab discovery-demo --backend opencl`. Add `--device 0:0` to select a
specific platform and device from `norisk-lab status`. The GPU request requires
a GPU-class OpenCL device. The FP32 winning circuit is checked against NumPy
and the receipt records device/driver identity and probability differences.
The separate `opencl-cpu` backend exercises the same kernels on a CPU OpenCL
device for verification.

On the target Windows machine, `START_UNIFIED_LAB.bat --verify-gpu` installs
the GPU extra and runs the short synthetic comparison. It prints the location
of the JSON receipt, which records the result and, on success, the OpenCL GPU
and CPU parity measurements. To verify a particular GPU on a multi-GPU system,
find its selector in `norisk-lab status` and pass it to `synthetic-demo --backend
opencl --device 0:0`, replacing `0:0` with that selector. These commands do not
submit historical jobs.

## Optional vendor runs

| Engine | Setup | Command |
| --- | --- | --- |
| NautilusTrader | Install `.[nautilus]` | `norisk-lab nautilus-demo` |
| LEAN | Build and configure the [pinned local Docker image](UNIFIED_LEAN_RUNTIME_2026-11-05.md) | `norisk-lab lean-demo` |
| FinRL | Set `NRFX_FINRL_SOURCE` to a checkout at `7e98df461cbc7772f16a545a2f13b521e5d0b8f4`. Install Torch 2.7.1 CPU, Stable-Baselines3 2.6.0, Gymnasium 1.1.1 and Matplotlib 3.10.3. | `norisk-lab finrl-demo` or `norisk-lab finrl-train-demo` |

LEAN and Nautilus record vendor-native simulated orders and fills on invented
BID/ASK bars. FinRL runs the pinned StockTradingEnv and reconciles native share changes,
fees and equity. Its optional PPO job trains for 512 CPU steps on one invented
fixture and freezes the policy before evaluation on a separately seeded
invented fixture. Both policy hashes and both fixture hashes are retained. Native vendor results use
each engine's own cost and fill model. The canonical reference/fast parity gate
is a separate check within the discovery job.

## Import earlier work

```console
norisk-lab import-legacy /path/to/legacy/repository --format frozen-files
norisk-lab import-legacy /path/to/research.sqlite3 --format durable-sqlite
norisk-lab import-proposals /path/to/formulas.json
norisk-lab work-once
```

The legacy source is read as a snapshot. Frozen requests are validated and
deduplicated by fingerprint. The dashboard shows their observed source state
and holds them apart from runnable jobs. The proposal file uses the
`NRFX_EXTERNAL_FORMULA_INTAKE_V1` contract from
`scripts/import_external_formula_proposals.py`. The lab accepts up to 16 typed
formulas per batch. The RD-Agent and TradingAgents fields identify the declared
source revision. The lab evaluates the formulas on an invented fixture with
both canonical execution engines. The default discovery campaign also uses the
pinned RD-Agent bandit to select a proposal family and the pinned
TradingAgents rating parser to reconcile synthetic labels from canonical
results. `norisk-lab agent-components-demo` runs the component path on its own.
The vendored components carry their original licenses and verified source
digests.

## Native agent workflows

The dashboard and CLI offer explicit jobs for the pinned upstream workflows.
They use separate Python environments from the lab. Both default to fixed
structured replies so the official orchestration can be checked without
credentials or inference.

| Job | Runtime configuration | Command |
| --- | --- | --- |
| TradingAgents | `NRFX_TRADINGAGENTS_PYTHON` points to a separate interpreter with the pinned TradingAgents revision installed | `norisk-lab tradingagents-demo` |
| RD-Agent | `NRFX_RDAGENT_PYTHON` points to the isolated interpreter and `NRFX_RDAGENT_CHECKOUT` to the clean pinned checkout | `norisk-lab rdagent-demo` |

For TradingAgents, install the exact revision in the separate environment:

```console
python -m pip install "tradingagents @ git+https://github.com/TauricResearch/TradingAgents.git@9fa1196fffbcfd9de5146d2dd2869df84ab99838"
```

For RD-Agent, install the proposal dependencies in its separate environment
and keep the source checkout at the pinned commit:

```console
python -m pip install -r scripts/rdagent_synthetic/requirements.txt
git clone https://github.com/microsoft/RD-Agent.git rdagent-upstream
git -C rdagent-upstream checkout 484776c211e4fbbeef03e0ec00d6bbee7362a4f4
```

The selected native graph runs the market analyst with invented bars and
isolated fixture tools, followed by the bull/bear, research, trader, risk and
portfolio nodes. RD-Agent runs the native Qlib factor hypothesis generator
and experiment conversion from `microsoft/RD-Agent` revision
`484776c211e4fbbeef03e0ec00d6bbee7362a4f4`. Its allowlisted formula proposals
flow into the lab's reference/fast parity checks. Its experiment record
contains proposed tasks. The lab executes no agent-generated code or Qlib backtest.

For model inference, explicitly choose `--mode ollama` and configure a local
model through `NRFX_TRADINGAGENTS_OLLAMA_MODEL` or `NRFX_RDAGENT_OLLAMA_MODEL`.
Both clients use the fixed loopback service at `127.0.0.1:11434`. TradingAgents
requires a local GGUF model with tool calling. For RD-Agent, set
`NRFX_RDAGENT_OLLAMA_DIGEST` to the model's full digest returned by the local
`/api/tags` endpoint. The saved receipt distinguishes an upstream workflow run
with fixed replies from one with actual model inference.
