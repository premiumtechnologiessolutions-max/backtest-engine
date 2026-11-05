import importlib.util
import unittest
from unittest.mock import patch

import numpy as np

from norisk_quant.quantum_optimizer import BinaryProblem
from norisk_quant.quantum_backends import (
    BackendUnavailable, backend_capabilities, solve_problem, statevector_probabilities,
)


class QuantumBackendTests(unittest.TestCase):
    def test_multiple_layers_match_dense_matrix_oracle(self):
        energy = np.array([0., 1., 4., -2., 2., 3., -3., 5.])
        angles = [(.4, -.8), (-.7, .2)]
        state = np.ones(8, dtype=complex) / np.sqrt(8)
        for gamma, beta in angles:
            rotation = np.array([[np.cos(beta), -1j*np.sin(beta)],
                                 [-1j*np.sin(beta), np.cos(beta)]])
            state = np.kron(np.kron(rotation, rotation), rotation) @ (
                np.exp(-1j*gamma*energy) * state)
        np.testing.assert_allclose(statevector_probabilities(energy, angles), abs(state)**2, atol=1e-12)

    def test_numpy_solve_does_not_import_pennylane(self):
        problem = BinaryProblem(('a', 'b'), (-2., -1.), ((0., 0.), (0., 0.)), 1, 5.)
        with patch('norisk_quant.quantum_backends.importlib.util.find_spec', side_effect=AssertionError):
            result = solve_problem(problem, evaluations=2)
        self.assertEqual(result['backend_adapter'], 'numpy')
        self.assertFalse(result['gpu_used'])

    def test_missing_optional_backend_explicit(self):
        with patch('norisk_quant.quantum_backends.importlib.util.find_spec', return_value=None):
            with self.assertRaises(BackendUnavailable):
                statevector_probabilities([0., 1.], [[.3, .2]], backend='pennylane')

    def test_unproven_gpu_is_not_enabled(self):
        self.assertFalse(backend_capabilities()['gpu']['execution_enabled'])
        with self.assertRaises(ValueError):
            statevector_probabilities([0., 1.], [[.3, .2]], backend='pennylane', device='lightning.gpu')

    def test_invalid_parameters(self):
        for angles in ([], [[True, 0.]], [[float('inf'), 0.]], [[1.]]):
            with self.assertRaises(ValueError):
                statevector_probabilities([0., 1.], angles)

    @unittest.skipUnless(importlib.util.find_spec('pennylane'), 'optional PennyLane is not installed')
    def test_pennylane_wire_order_and_layers(self):
        energy = [0., 1., 3., -2., 5., -1., 4., 2.]
        angles = [[.6, -.2], [-.4, .7]]
        np.testing.assert_allclose(
            statevector_probabilities(energy, angles, backend='pennylane'),
            statevector_probabilities(energy, angles), atol=1e-10,
        )
