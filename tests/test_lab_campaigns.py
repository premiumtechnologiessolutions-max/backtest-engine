import importlib.util
from pathlib import Path
import tempfile
import unittest
import pandas as pd
from norisk_quant.lab_coordinator import LabCoordinator, validate_spec
from norisk_quant.lab_campaigns import normalize_canonical_ledger


class DiscoveryIntegrationTests(unittest.TestCase):
    def test_two_generations_multiasset_quantum_and_shared_portfolio(self):
        with tempfile.TemporaryDirectory() as d:
            lab=LabCoordinator(Path(d)/'lab.db')
            lab.submit({'kind':'synthetic_discovery','bars':240,'evaluations':2})
            job=lab.run_one()
            self.assertEqual(job['state'],'SUCCEEDED', job['error'])
            result=job['result']
            self.assertEqual(result['discovery']['evaluated'],16)
            self.assertEqual(len({c['spec']['identity'] for c in result['candidates']}),8)
            self.assertEqual({c['generation'] for c in result['candidates']},{0,1})
            self.assertTrue(all(c['parity_passed'] for c in result['candidates']))
            self.assertTrue(any(c['spec']['parent_id'] for c in result['candidates'] if c['generation']==1))
            self.assertLessEqual(result['portfolio']['summary']['peak_positions'],2)
            self.assertEqual(len(result['selection']['selected']),4)
            self.assertFalse(result['market_data_accessed'])
            self.assertGreater(len(lab.job(job['id'])['events']),16)
    def test_intrabar_closure_known_only_at_candle_end(self):
        at=pd.Timestamp('2024-01-08T00:01:00Z')
        frame=pd.DataFrame([{'entry_at':at,'closed_at':at,'signal_at':at,
                             'exit_reason':'stop'},
                            {'entry_at':at,'closed_at':at,'signal_at':at,
                             'exit_reason':'open_stop'}])
        records=normalize_canonical_ledger(frame,'candidate')
        self.assertEqual(pd.Timestamp(records[0]['closed_at']),at+pd.Timedelta(minutes=1))
        self.assertEqual(pd.Timestamp(records[1]['closed_at']),at)
        self.assertEqual(frame.iloc[0]['closed_at'],at)
    def test_spec_bounds_and_no_external_paths(self):
        for spec in [{'kind':'synthetic_discovery','bars':10000},
                     {'kind':'synthetic_discovery','evaluations':100},
                     {'kind':'nautilus_synthetic','path':'Gold.zip'}]:
            with self.assertRaises(ValueError):
                validate_spec(spec)
    @unittest.skipUnless(importlib.util.find_spec('nautilus_trader'),'optional vendor absent')
    def test_real_vendor_dispatch_is_persisted(self):
        with tempfile.TemporaryDirectory() as d:
            lab=LabCoordinator(Path(d)/'lab.db')
            lab.submit({'kind':'nautilus_synthetic','bars':60,'seed':7})
            job=lab.run_one()
            self.assertEqual(job['state'],'SUCCEEDED',job['error'])
            self.assertTrue(job['result']['runtime_executed'])
            self.assertGreater(job['result']['fills_count'],0)
