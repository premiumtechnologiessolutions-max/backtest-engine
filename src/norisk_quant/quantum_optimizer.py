"""Bounded local QAOA simulation for supplied binary optimization problems.

No market ingestion, training, broker access or vendor subprocesses. NumPy is
an actual statevector simulator, not quantum hardware or a speedup claim.
Bit i in an integer corresponds to variable i (little-endian).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BinaryProblem:
    labels: tuple[str, ...]
    linear: tuple[float, ...]
    quadratic: tuple[tuple[float, ...], ...]
    select_count: int
    penalty: float

    def __post_init__(self):
        n = len(self.labels)
        if not 1 <= n <= 16 or len(set(self.labels)) != n:
            raise ValueError("Require 1..16 distinct variable labels")
        if any(type(x) is not str or not x or len(x) > 80 for x in self.labels):
            raise ValueError("Invalid variable label")
        if len(self.linear) != n or len(self.quadratic) != n or any(len(r) != n for r in self.quadratic):
            raise ValueError("Coefficient shape mismatch")
        values = [*self.linear, *(x for row in self.quadratic for x in row), self.penalty]
        if any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e9 for x in values):
            raise ValueError("Require finite bounded numeric coefficients")
        if type(self.select_count) is not int or not 0 <= self.select_count <= n or self.penalty <= 0:
            raise ValueError("Invalid cardinality or penalty")
        # Store each pair once, so imported QUBO matrix semantics are explicit.
        if any(self.quadratic[i][j] != 0 for i in range(n) for j in range(i + 1)):
            raise ValueError("Quadratic matrix must be strictly upper triangular")

    @classmethod
    def from_dict(cls, value):
        if type(value) is not dict or set(value) != {'labels', 'linear', 'quadratic', 'select_count', 'penalty'}:
            raise ValueError("Unexpected binary problem fields")
        return cls(tuple(value['labels']), tuple(value['linear']),
                   tuple(tuple(row) for row in value['quadratic']), value['select_count'], value['penalty'])

    def payload(self):
        return dict(labels=list(self.labels), linear=list(self.linear),
                    quadratic=[list(r) for r in self.quadratic],
                    select_count=self.select_count, penalty=self.penalty)

    def energies(self):
        states = np.arange(1 << len(self.labels), dtype=np.uint32)
        bits = ((states[:, None] >> np.arange(len(self.labels))) & 1).astype(float)
        raw = bits @ np.asarray(self.linear, dtype=float)
        for i in range(len(self.labels)):
            for j in range(i + 1, len(self.labels)):
                raw += self.quadratic[i][j] * bits[:, i] * bits[:, j]
        feasible = bits.sum(axis=1) == self.select_count
        penalized = raw + self.penalty * (bits.sum(axis=1) - self.select_count) ** 2
        return bits, raw, penalized, feasible


def probabilities(energies, parameters):
    """Apply exp(-i gamma C) then exp(-i beta sum X) for each QAOA layer."""
    energies = np.asarray(energies, dtype=float)
    size = len(energies)
    if size < 2 or size > 65536 or size & (size - 1) or not np.isfinite(energies).all():
        raise ValueError("Invalid bounded statevector energy table")
    if type(parameters) not in (tuple, list) or not 1 <= len(parameters) <= 8:
        raise ValueError("Require 1..8 QAOA layers")
    state = np.ones(size, dtype=np.complex128) / math.sqrt(size)
    for pair in parameters:
        if len(pair) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in pair):
            raise ValueError("Invalid QAOA angles")
        gamma, beta = pair
        state *= np.exp(-1j * gamma * energies)
        c, s = math.cos(beta), -1j * math.sin(beta)
        for bit in range(size.bit_length() - 1):
            blocks = state.reshape(-1, 2, 1 << bit)
            first, second = blocks[:, 0, :].copy(), blocks[:, 1, :].copy()
            blocks[:, 0, :] = c * first + s * second
            blocks[:, 1, :] = s * first + c * second
    return np.abs(state) ** 2


def solve(problem: BinaryProblem, *, layers=1, evaluations=64, seed=0):
    if type(layers) is not int or not 1 <= layers <= 8:
        raise ValueError("Require 1..8 layers")
    if type(evaluations) is not int or not 1 <= evaluations <= 4096:
        raise ValueError("Require 1..4096 objective evaluations")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("Invalid seed")
    bits, raw, energy, feasible = problem.energies()
    # Scaling changes angle units only; reports retain original energies.
    scale = max(1.0, float(np.max(np.abs(energy))))
    rng = np.random.default_rng(seed)
    best = None
    for _ in range(evaluations):
        angles = [tuple(map(float, r)) for r in rng.uniform(-math.pi, math.pi, (layers, 2))]
        probs = probabilities(energy / scale, angles)
        expectation = float(probs @ energy)
        if best is None or expectation < best[0]:
            best = expectation, angles, probs
    expectation, angles, probs = best
    indices = np.flatnonzero(feasible)
    # Exact enumeration is an independent classical objective baseline. It is
    # never reported as a discovered QAOA answer.
    exact = int(indices[np.argmin(raw[indices])])
    chosen = int(indices[np.argmax(probs[indices])])
    payload = problem.payload()
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {
        'schema': 'NRFX_LOCAL_QAOA_V1', 'problem_sha256': digest,
        'backend': 'numpy_cpu_statevector', 'quantum_hardware_used': False,
        'gpu_used': False, 'quantum_advantage_proven': False,
        'optimization': 'seeded_random_angle_search', 'seed': seed,
        'layers': layers, 'objective_evaluations': evaluations,
        'parameters': [list(pair) for pair in angles], 'expected_penalized_objective': expectation,
        'feasible_probability': float(probs[feasible].sum()),
        'selected': [name for name, x in zip(problem.labels, bits[chosen]) if x],
        'selected_probability': float(probs[chosen]), 'selected_objective': float(raw[chosen]),
        'classical_exact_selected': [name for name, x in zip(problem.labels, bits[exact]) if x],
        'classical_exact_objective': float(raw[exact]),
        'objective_gap': float(raw[chosen] - raw[exact]),
        'selection_policy': 'highest_probability_feasible_state_not_exact_optimum',
        'market_data_accessed': False, 'trades_executed': False,
    }
