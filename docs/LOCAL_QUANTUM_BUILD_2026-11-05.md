# Local Quantum construction increment — 2026-11-05

## Implemented

- Actual NumPy complex statevector QAOA: diagonal problem evolution and Rx mixers.
- Strict upper-triangular binary objective, cardinality penalty, at most 16 qubits.
- Seeded bounded random-angle optimization (not an advanced variational optimizer).
- Highest-probability feasible answer, compared separately with exact enumeration.
- Explicit CPU backend and package-presence report; no GPU compatibility inference.
- Atomic immutable JSON output with input and source digests.
- Independent dense-matrix oracle test; no historical market research performed.

Run after normal project installation:

```console
python -m norisk_quant.quantum_workflow capabilities
python -m norisk_quant.quantum_workflow solve problem.json --out result.json --evaluations 64
```

Example construction-only problem (coefficients invented, not trading evidence):

```json
{"labels":["a","b","c"],"linear":[-3,-2,-1],"quadratic":[[0,4,0],[0,0,0],[0,0,0]],"select_count":2,"penalty":12}
```

Bit i corresponds to variable i. Objective is sum(linear[i]*x[i]) plus
sum(quadratic[i][j]*x[i]*x[j], i<j). Penalty multiplies (sum(x)-select_count)^2.
Raw objective and feasibility are reported separately; a penalty need not make
the unconstrained optimum feasible. Postselection does not prove quantum advantage.
Statevector memory/time grows exponentially. Exact enumeration is bounded by the
same limit and is not scalable portfolio optimization.

## Boundaries and remaining integration

This is original project code, not copied PennyLane/Qiskit internals. It does not
yet use those libraries. Package presence does not mean a usable device.
GPU execution, PennyLane/Lightning adapters, Qiskit comparison, measured device
limits, durable scheduler integration, cancellation/resume of optimization,
market-to-objective compilation and unified UI remain unimplemented.
No claim of profitability, quantum advantage or complete platform readiness.
No Gold archive, broker, external runner or autonomous service is accessed.

Validation: five construction unit tests, including a dense-matrix QAOA oracle,
seeded reproducibility, independent objective baseline, immutable reports and
invalid inputs. Full repository CI must run on the resulting commit.
