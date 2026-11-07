"""Synthetic-only contract checks; no market data or workers."""
import unittest
from scripts.construction_job_ledger import ConstructionLedger


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = ConstructionLedger()
        self.spec = dict(kind='static_audit', name='check_schema',
                         source_commit='a' * 40,
                         fixture='tests/fixtures/synthetic/sample.json')

    def test_records_inert_entry(self):
        entry = self.ledger.record(self.spec)
        self.assertEqual(entry.state, 'RECORDED_NOT_EXECUTED')
        self.assertEqual(len(entry.digest), 64)

    def test_deduplicates_equivalent_descriptors(self):
        self.assertIs(self.ledger.record(self.spec), self.ledger.record(dict(self.spec)))
        self.assertEqual(len(self.ledger.snapshot()), 1)

    def test_rejects_market_job(self):
        self.spec['kind'] = 'backtest'
        with self.assertRaises(ValueError):
            self.ledger.record(self.spec)
        self.assertEqual(self.ledger.snapshot(), ())

    def test_commit_changes_identity(self):
        self.ledger.record(self.spec)
        self.spec['source_commit'] = 'b' * 40
        self.ledger.record(self.spec)
        self.assertEqual(len(self.ledger.snapshot()), 2)

    def test_no_mutable_snapshot(self):
        self.ledger.record(self.spec)
        with self.assertRaises(Exception):
            self.ledger.snapshot()[0].state = 'EXECUTED'


if __name__ == '__main__':
    unittest.main()
