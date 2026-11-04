"""Synthetic-only tests for read-only construction manifest."""
import unittest
from dataclasses import FrozenInstanceError

from scripts.construction_job_ledger import ConstructionLedger, LedgerEntry
from scripts.construction_job_manifest import manifest


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.ledger = ConstructionLedger()
        self.spec = {"kind": "static_audit", "name": "schema",
                     "source_commit": "a" * 40,
                     "fixture": "tests/fixtures/synthetic/sample.json"}

    def test_empty_manifest_is_explicitly_inert(self):
        result = manifest(self.ledger)
        self.assertEqual(result["recorded_specs"], 0)
        self.assertEqual(result["completed_jobs"], 0)
        self.assertIsNone(result["monthly_pnl"])
        self.assertIsNone(result["floating_drawdown"])
        self.assertFalse(result["execution_started"])
        self.assertFalse(result["market_data_accessed"])

    def test_deduplicated_manifest_is_stable(self):
        self.ledger.record(self.spec)
        first = manifest(self.ledger)
        self.ledger.record(dict(self.spec))
        self.assertEqual(first, manifest(self.ledger))
        self.assertEqual(first["recorded_specs"], 1)
        self.assertEqual(len(first["records_sha256"]), 64)

    def test_commit_changes_manifest(self):
        before = manifest(self.ledger)["records_sha256"]
        self.ledger.record(self.spec)
        self.assertNotEqual(before, manifest(self.ledger)["records_sha256"])

    def test_rejects_wrong_ledger(self):
        with self.assertRaises(TypeError):
            manifest({})

    def test_rejects_corrupt_record(self):
        self.ledger._entries["bad"] = LedgerEntry("invalid", "a" * 40)
        with self.assertRaises(ValueError):
            manifest(self.ledger)

    def test_rejects_false_executed_state(self):
        self.ledger._entries["bad"] = LedgerEntry("a" * 64, "b" * 40, "EXECUTED")
        with self.assertRaises(ValueError):
            manifest(self.ledger)


if __name__ == "__main__":
    unittest.main()
