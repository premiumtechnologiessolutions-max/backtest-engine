import os
import unittest
from unittest.mock import patch

import numpy as np

from norisk_quant.quantum_backends import (
    BackendUnavailable, backend_capabilities, opencl_device_identity,
    solve_problem, statevector_probabilities,
)
from norisk_quant.quantum_optimizer import BinaryProblem


class OpenCLBackendTests(unittest.TestCase):
    def test_gpu_selection_never_uses_cpu(self):
        cpu = {'selector': '0:0', 'device_type': 'cpu', 'compatible': True}
        with patch('norisk_quant.quantum_opencl._scan', return_value=(
            object(), [(cpu, object())], 'DEVICE_DISCOVERED',
        )):
            self.assertEqual(opencl_device_identity('opencl-cpu', '0:0'), cpu)
            self.assertFalse(backend_capabilities()['gpu']['execution_enabled'])
            with self.assertRaises(BackendUnavailable):
                opencl_device_identity('opencl', '0:0')
            with self.assertRaises(BackendUnavailable):
                statevector_probabilities([0., 1.], [[.3, .2]], backend='opencl')

    def test_discovery_does_not_claim_circuit_execution(self):
        gpu = {'selector': '0:0', 'device_type': 'gpu', 'compatible': True}
        with patch('norisk_quant.quantum_opencl._scan', return_value=(
            object(), [(gpu, object())], 'DEVICE_DISCOVERED',
        )):
            capabilities = backend_capabilities()
            self.assertEqual(capabilities['backends']['opencl']['devices'], [gpu])
            self.assertTrue(capabilities['gpu']['execution_enabled'])
            self.assertFalse(capabilities['gpu']['execution_verified'])

    def test_malformed_selector_rejected_before_probing(self):
        with patch('norisk_quant.quantum_opencl._scan', side_effect=AssertionError):
            for selector in (False, 'cpu', '1', '00:1', '0:-1', '0:00000'):
                with self.subTest(selector=selector), self.assertRaises(ValueError):
                    statevector_probabilities([0., 1.], [[.3, .2]],
                                              backend='opencl', device=selector)

    def test_cpu_opencl_runs_kernels_and_matches_numpy(self):
        capability = backend_capabilities()['backends']['opencl-cpu']
        if not capability['available'] and os.environ.get('NRFX_REQUIRE_OPENCL_CPU') != '1':
            self.skipTest('optional CPU OpenCL device unavailable')
        self.assertTrue(capability['available'], capability)
        energy = np.random.default_rng(12).uniform(-1., 1., 65536)
        angles = [[.6, -.2], [-.4, .7], [.9, -1.3]]
        actual = statevector_probabilities(energy, angles, backend='opencl-cpu')
        expected = statevector_probabilities(energy, angles)
        self.assertLess(float(np.abs(actual - expected).sum() / 2), 1e-4)
        self.assertLess(float(np.abs(actual - expected).max()), 2e-5)
        self.assertAlmostEqual(float(actual.sum()), 1.)
        self._verify_solver('opencl-cpu', 'cpu')

    def test_gpu_opencl_solver_when_device_present(self):
        if not backend_capabilities()['backends']['opencl']['available']:
            self.skipTest('optional GPU OpenCL device unavailable')
        self._verify_solver('opencl', 'gpu')

    def _verify_solver(self, backend, kind):
        problem = BinaryProblem(('a', 'b', 'c'), (-2., -1., -.3),
                                ((0., .6, -.1), (0., 0., .2), (0., 0., 0.)), 2, 8.)
        device = opencl_device_identity(backend)
        result = solve_problem(problem, backend=backend, device=device['selector'],
                               evaluations=5, layers=2, seed=17)
        baseline = solve_problem(problem, evaluations=5, layers=2, seed=17)
        self.assertEqual(result['selected'], baseline['selected'])
        self.assertEqual(result['classical_exact_selected'], baseline['classical_exact_selected'])
        self.assertEqual(result['gpu_used'], kind == 'gpu')
        self.assertEqual(result['opencl_device'], device)
        self.assertEqual(result['opencl_device']['device_type'], kind)
        self.assertEqual(result['precision'], 'float32')
        self.assertEqual(result['opencl_numpy_parity']['scope'], 'winning_circuit')
        self.assertLess(result['opencl_numpy_parity']['total_variation_distance'], 1e-4)
