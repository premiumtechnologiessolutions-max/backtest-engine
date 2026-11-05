# Native LEAN synthetic runtime

Build the optional runtime from the official QuantConnect LEAN checkout at
`9ecfed98339c27849a2a708edc03455caf151e91`. The build needs Git, Bash and a local
Docker daemon with Linux containers. It retrieves .NET SDK/runtime images and
restores upstream NuGet dependencies. The build context contains pinned source,
market-hours metadata, symbol-properties metadata and the fixed NRFX algorithm.

```bash
export NRFX_LEAN_RUNTIME_IMAGE="$(bash scripts/lean_synthetic/build.sh /path/to/pinned/Lean)"
norisk-lab lean-demo --seed 7
```

The launcher gets invented native EURUSD quote ZIPs for its bounded run. Docker
uses the local image ID, disabled networking, a read-only root filesystem and a
non-root user. It mounts only generated inputs and an empty results directory.
The engine submits and closes market orders in the local backtesting mode. The
adapter reconciles the native order-event file with the closed trades from the
native result before marking the job successful. LEAN's vendor fill and fee
models remain distinct from the project's canonical XAUUSD model.

Use `NRFX_REQUIRE_LEAN=1 python -m pytest -q tests/test_lab_lean.py` to require
native execution in the verification suite. The GitHub workflow prepares the
same upstream launcher and requires both native execution and durable dispatch.
