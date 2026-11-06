"""Bounded CPU and OpenCL quantum backends with explicit device selection.

The adapters simulate a QAOA circuit. OpenCL computes statevector operations
on its chosen device and verifies the winning circuit against NumPy.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math

import numpy as np

from .quantum_opencl import (
    OPENCL_BACKENDS, OpenCLStatevector, OpenCLUnavailable, opencl_capabilities,
    opencl_device_identity as _opencl_device_identity, validate_opencl_selector,
)
from .quantum_optimizer import BinaryProblem, probabilities, solve

CPU_DEVICES = frozenset({'default.qubit', 'lightning.qubit'})


class BackendUnavailable(RuntimeError):
    """Requested optional quantum backend cannot be used on this host."""


def backend_capabilities() -> dict:
    opencl = opencl_capabilities()
    gpu = opencl['opencl']
    return {
        'default': 'numpy',
        'backends': {
            'numpy': {'installed': True, 'execution': 'cpu_statevector'},
            'pennylane': {
                'installed': importlib.util.find_spec('pennylane') is not None,
                'allowed_devices': sorted(CPU_DEVICES),
                'device_initialization_verified': False,
            },
            **opencl,
        },
        'gpu': {
            'compatibility': 'DEVICE_AVAILABLE_UNVERIFIED' if gpu['available'] else gpu['status'],
            'execution_enabled': gpu['available'],
            'execution_verified': False,
        },
        'quantum_hardware': False,
        'quantum_advantage_proven': False,
    }


def opencl_device_identity(backend, device=None):
    if backend not in OPENCL_BACKENDS:
        raise ValueError('Unsupported OpenCL backend')
    try:
        return _opencl_device_identity(backend, device)
    except OpenCLUnavailable as exc:
        raise BackendUnavailable(str(exc)) from exc


def _validate_angles(energies, parameters):
    e = np.asarray(energies, dtype=float)
    if (e.ndim != 1 or len(e) < 2 or len(e) > 65536
            or len(e) & (len(e) - 1) or not np.isfinite(e).all()):
        raise ValueError('Invalid bounded statevector energy table')
    if type(parameters) not in (tuple, list) or not 1 <= len(parameters) <= 8:
        raise ValueError('Require 1..8 QAOA layers')
    for pair in parameters:
        if type(pair) not in (tuple, list) or len(pair) != 2:
            raise ValueError('Invalid QAOA angles')
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in pair):
            raise ValueError('Invalid QAOA angles')
    return e


def statevector_probabilities(energies, parameters, *, backend='numpy', device=None):
    """Return probabilities in integer order, with variable i in bit i."""
    e = _validate_angles(energies, parameters)
    if backend == 'numpy':
        if device not in (None, 'cpu'):
            raise ValueError('NumPy backend supports only CPU')
        return probabilities(e, parameters)
    if backend in OPENCL_BACKENDS:
        try:
            return OpenCLStatevector(e, backend, device).probabilities(parameters)
        except OpenCLUnavailable as exc:
            raise BackendUnavailable(str(exc)) from exc
    if backend != 'pennylane':
        raise ValueError('Unsupported backend')
    device = device or 'default.qubit'
    if device not in CPU_DEVICES:
        raise ValueError('Only explicitly supported PennyLane CPU devices are enabled')
    if importlib.util.find_spec('pennylane') is None:
        raise BackendUnavailable('PennyLane is not installed; install the optional quantum extra')
    try:
        import pennylane as qml
        n = len(e).bit_length() - 1
        dev = qml.device(device, wires=n, shots=None)
        # PennyLane orders its first listed wire as the most significant bit.
        # Reversing wire order preserves the project's little-endian contract.
        ordering = list(reversed(range(n)))

        @qml.qnode(dev, interface=None, diff_method=None)
        def circuit():
            for wire in range(n):
                qml.Hadamard(wires=wire)
            for gamma, beta in parameters:
                qml.DiagonalQubitUnitary(np.exp(-1j * gamma * e), wires=ordering)
                for wire in range(n):
                    qml.RX(2 * beta, wires=wire)
            return qml.probs(wires=ordering)

        result = np.asarray(circuit(), dtype=float)
    except Exception as exc:
        raise BackendUnavailable(f'PennyLane device {device} failed: {type(exc).__name__}') from exc
    if (result.shape != e.shape or not np.isfinite(result).all()
            or (result < -1e-12).any() or abs(float(result.sum()) - 1) > 1e-8):
        raise BackendUnavailable('Quantum device returned invalid probabilities')
    return result


def solve_problem(problem: BinaryProblem, *, backend='numpy', layers=1,
                  evaluations=64, seed=0, device=None) -> dict:
    if backend == 'numpy':
        if device not in (None, 'cpu'):
            raise ValueError('NumPy backend supports only CPU')
        result = solve(problem, layers=layers, evaluations=evaluations, seed=seed)
        result['backend_adapter'] = 'numpy'
        return result
    if backend != 'pennylane' and backend not in OPENCL_BACKENDS:
        raise ValueError('Unsupported backend')
    if (type(layers) is not int or not 1 <= layers <= 8
            or type(evaluations) is not int or not 1 <= evaluations <= 4096
            or type(seed) is not int or not 0 <= seed < 2**32):
        raise ValueError('Invalid bounded optimization settings')
    bits, raw, energy, feasible = problem.energies()
    scale = max(1.0, float(np.max(np.abs(energy))))
    scaled_energy = energy / scale
    rng = np.random.default_rng(seed)
    best = None
    simulator = None
    try:
        if backend in OPENCL_BACKENDS:
            simulator = OpenCLStatevector(scaled_energy, backend, device)
        for _ in range(evaluations):
            angles = [list(map(float, row)) for row in
                      rng.uniform(-math.pi, math.pi, (layers, 2))]
            if simulator is None:
                probs = statevector_probabilities(scaled_energy, angles, backend=backend, device=device)
            else:
                probs = simulator.probabilities(angles)
            expectation = float(probs @ energy)
            if best is None or expectation < best[0]:
                best = expectation, angles, probs
    except OpenCLUnavailable as exc:
        raise BackendUnavailable(str(exc)) from exc
    expectation, angles, probs = best
    backend_details = {'backend': f'pennylane:{device or "default.qubit"}',
                       'backend_adapter': backend, 'gpu_used': False}
    if simulator is not None:
        error = np.abs(probs - probabilities(scaled_energy, angles))
        max_error = float(error.max())
        total_variation = float(error.sum() / 2)
        max_tolerance, tv_tolerance = 2e-5, 1e-4
        if max_error > max_tolerance or total_variation > tv_tolerance:
            raise BackendUnavailable('OpenCL circuit exceeded NumPy reference tolerances')
        backend_details = {
            'backend': f'{backend}:{simulator.device["selector"]}',
            'backend_adapter': backend,
            'gpu_used': simulator.device['device_type'] == 'gpu',
            'opencl_device': simulator.device,
            'precision': 'float32',
            'opencl_numpy_parity': {
                'scope': 'winning_circuit',
                'max_absolute_probability_error': max_error,
                'max_absolute_probability_error_tolerance': max_tolerance,
                'total_variation_distance': total_variation,
                'total_variation_distance_tolerance': tv_tolerance,
            },
        }
    indices = np.flatnonzero(feasible)
    exact = int(indices[np.argmin(raw[indices])])
    chosen = int(indices[np.argmax(probs[indices])])
    digest = hashlib.sha256(json.dumps(problem.payload(), sort_keys=True,
                                      allow_nan=False).encode()).hexdigest()
    return {
        'schema': 'NRFX_LOCAL_QAOA_V1', 'problem_sha256': digest,
        **backend_details,
        'quantum_hardware_used': False, 'quantum_advantage_proven': False,
        'optimization': 'seeded_random_angle_search', 'seed': seed,
        'layers': layers, 'objective_evaluations': evaluations,
        'parameters': angles, 'expected_penalized_objective': expectation,
        'feasible_probability': float(probs[feasible].sum()),
        'selected': [name for name, x in zip(problem.labels, bits[chosen]) if x],
        'selected_probability': float(probs[chosen]),
        'selected_objective': float(raw[chosen]),
        'classical_exact_selected': [name for name, x in zip(problem.labels, bits[exact]) if x],
        'classical_exact_objective': float(raw[exact]),
        'objective_gap': float(raw[chosen] - raw[exact]),
        'selection_policy': 'highest_probability_feasible_state_not_exact_optimum',
        'market_data_accessed': False, 'trades_executed': False,
    }
