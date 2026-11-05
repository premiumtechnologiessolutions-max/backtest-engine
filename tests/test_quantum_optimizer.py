import json
import numpy as np
import unittest
import tempfile
from pathlib import Path
from norisk_quant.quantum_optimizer import BinaryProblem, probabilities, solve
from norisk_quant.quantum_workflow import run_problem


def problem():
    return BinaryProblem(('a', 'b', 'c'), (-3., -2., -1.),
                         ((0., 4., 0.), (0., 0., 0.), (0., 0., 0.)), 2, 12.)


def test_independent_dense_matrix_qaoa():
    energy = np.array([0., 1., 3., -2.])
    gamma, beta = .7, -.3
    rotation = np.array([[np.cos(beta), -1j*np.sin(beta)],
                         [-1j*np.sin(beta), np.cos(beta)]])
    expected = np.kron(rotation, rotation) @ (np.exp(-1j*gamma*energy)/2)
    assert np.allclose(probabilities(energy, [(gamma, beta)]), abs(expected)**2)


def test_baseline_and_reproducibility():
    first = solve(problem(), evaluations=12, seed=8)
    assert first == solve(problem(), evaluations=12, seed=8)
    assert first['classical_exact_selected'] == ['a', 'c']
    assert first['classical_exact_objective'] == -4
    assert first['objective_gap'] >= 0
    assert len(first['selected']) == 2
    assert 0 <= first['feasible_probability'] <= 1.00000000001


def test_zero_angles_uniform():
    assert np.allclose(probabilities(np.arange(8), [(0., 0.)]), 1/8)


def check_report(tmp_path):
    source, target = tmp_path/'problem.json', tmp_path/'report.json'
    source.write_text(json.dumps(problem().payload()))
    result = run_problem(source, target, evaluations=2)
    assert json.loads(target.read_text()) == result
    with unittest.TestCase().assertRaises(FileExistsError):
        run_problem(source, target, evaluations=2)



class QuantumTests(unittest.TestCase):
    def test_dense_oracle(self):
        test_independent_dense_matrix_qaoa()
    def test_baseline(self):
        test_baseline_and_reproducibility()
    def test_uniform(self):
        test_zero_angles_uniform()
    def test_report(self):
        with tempfile.TemporaryDirectory() as directory:
            check_report(Path(directory))
    def test_invalid(self):
        for changes in [dict(penalty=float('nan')), dict(select_count=True), dict(select_count=4), dict(linear=(True,2,3))]:
            payload = problem().payload()
            payload.update(changes)
            with self.assertRaises(ValueError):
                BinaryProblem.from_dict(payload)
