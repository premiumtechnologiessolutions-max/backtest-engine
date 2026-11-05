import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from norisk_quant.lab_coordinator import LabCoordinator


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.database = Path(self.tmp.name)/'lab.db'
        self.lab = LabCoordinator(self.database)
    def tearDown(self):
        self.tmp.cleanup()
    def test_full_existing_engine_to_quantum_pipeline(self):
        job = self.lab.submit({'kind':'synthetic_campaign','bars':300,'evaluations':8})
        result = self.lab.run_one()
        self.assertEqual(result['state'], 'SUCCEEDED', result.get('error'))
        report = result['result']
        self.assertEqual(report['provenance'], 'SYNTHETIC_NOT_MARKET')
        self.assertEqual(len(report['candidates']), 4)
        self.assertTrue(all(c['parity_passed'] for c in report['candidates']))
        self.assertTrue(all(c['trades'] > 0 for c in report['candidates']))
        self.assertEqual(len(report['selection']['selected']), 2)
        self.assertGreaterEqual(report['selection']['objective_gap'], -1e-10)
        self.assertEqual(LabCoordinator(self.database).job(job['id'])['result'], report)
        self.assertEqual(self.lab.submit({'kind':'synthetic_campaign','bars':300,'evaluations':8})['id'], job['id'])
        self.assertEqual(self.lab.run_one()['state'], 'IDLE')
    def test_blocks_market_jobs_and_unknown_fields(self):
        for spec in [{'kind':'gold_campaign'}, {'kind':'synthetic_campaign','path':'private.zip'},
                     {'kind':'synthetic_campaign','bars':100000}, {'kind':'synthetic_campaign','seed':True}]:
            with self.assertRaises(ValueError):
                self.lab.submit(spec)
    def test_cancel_prevents_execution(self):
        job = self.lab.submit({'kind':'synthetic_campaign'})
        self.lab.cancel(job['id'])
        self.assertEqual(self.lab.run_one()['state'], 'IDLE')
    def test_code_drift_fails_closed(self):
        self.lab.submit({'kind':'synthetic_campaign'})
        with patch('norisk_quant.lab_coordinator.code_identity', return_value='different'):
            result = self.lab.run_one()
        self.assertEqual(result['state'], 'FAILED')
        self.assertIsNone(result['result'])
    def test_reference_disagreement_never_publishes(self):
        self.lab.submit({'kind':'synthetic_campaign','bars':240,'evaluations':1})
        with patch('norisk_quant.lab_coordinator._parity', side_effect=ValueError('mismatch')):
            result = self.lab.run_one()
        self.assertEqual(result['state'], 'FAILED')
        self.assertIsNone(result['result'])
