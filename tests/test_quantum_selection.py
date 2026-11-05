import unittest

import numpy as np

from norisk_quant.quantum_selection import compile_selection


def candidates():
    return [dict(id='a', expected_return=3., source_id='synthetic-1'),
            dict(id='b', expected_return=2., source_id='synthetic-1'),
            dict(id='c', expected_return=1., source_id='synthetic-2')]


class QuantumSelectionTests(unittest.TestCase):
    def test_all_binary_objectives_match_independent_matrix(self):
        cov = np.array([[2., .3, -.1], [.3, 1., .2], [-.1, .2, .8]])
        compiled = compile_selection(candidates(), cov.tolist(), 2, risk_aversion=.7)
        bits, raw, energy, feasible = compiled.problem.energies()
        for i, x in enumerate(bits):
            expected = .7 * x @ cov @ x - np.array([3., 2., 1.]) @ x
            self.assertAlmostEqual(raw[i], expected)
        # Automatic penalty makes every infeasible energy worse than a feasible optimum.
        self.assertGreater(energy[~feasible].min(), energy[feasible].min())
        self.assertEqual(compiled.manifest['source_ids'], ['synthetic-1', 'synthetic-2'])
        self.assertFalse(compiled.manifest['supplied_receipts_independently_verified'])

    def test_source_identity_changes_compilation(self):
        first = compile_selection(candidates(), np.eye(3).tolist(), 1)
        changed = candidates()
        changed[0]['source_id'] = 'different-source'
        second = compile_selection(changed, np.eye(3).tolist(), 1)
        self.assertNotEqual(first.manifest['compilation_sha256'], second.manifest['compilation_sha256'])

    def test_invalid_covariance(self):
        invalid = [[[1., 2.], [2., 1.]], [[1., 1.], [0., 1.]],
                   [[True, 0.], [0., 1.]], [[float('nan'), 0.], [0., 1.]]]
        for cov in invalid:
            with self.assertRaises(ValueError):
                compile_selection(candidates()[:2], cov, 1)

    def test_real_training_requires_receipt_identity(self):
        with self.assertRaises(ValueError):
            compile_selection(candidates(), np.eye(3).tolist(), 1, provenance='audited_training')
        rows = [dict(c, audit_receipt_sha256='a'*64) for c in candidates()]
        compiled = compile_selection(rows, np.eye(3).tolist(), 1, provenance='audited_training')
        self.assertFalse(compiled.manifest['supplied_receipts_independently_verified'])

    def test_source_set_and_duplicate_labels(self):
        with self.assertRaises(ValueError):
            compile_selection(candidates(), np.eye(3).tolist(), 1, source_ids=('wrong',))
        rows = candidates()
        rows[1]['id'] = 'a'
        with self.assertRaises(ValueError):
            compile_selection(rows, np.eye(3).tolist(), 1)
