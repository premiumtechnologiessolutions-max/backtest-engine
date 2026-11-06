"""Frozen source identity and held-state behavior across both legacy formats."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from norisk_quant.lab_jobs import JobStateError, JobStore
from norisk_quant.lab_legacy import import_legacy_queue
from scripts.durable_research_state import DurableResearchState
from scripts.research_job_queue import enqueue, frozen_request


class LegacyIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        (self.repo / 'docs').mkdir(parents=True)
        (self.repo / 'research').mkdir()
        (self.repo / 'docs/spec.md').write_text('Frozen fixture specification', encoding='utf-8')
        (self.repo / 'research/strategy_factory_registry.json').write_text('{}', encoding='utf-8')
        self.request = frozen_request(self.repo, 'NRF-FAC-001', 'docs/spec.md',
                                      'a'*40, '2020-01-01', '2020-01-31')
        self.store = JobStore(self.root / 'lab.sqlite3')

    def test_frozen_import_dedup_persistence_and_no_historical_claim(self):
        enqueue(self.repo, self.request)
        expected_bytes = (self.repo / 'reports/research_jobs' / (self.request['fingerprint'] + '.json')).read_bytes()
        report = import_legacy_queue(self.store, self.repo, source_format='frozen-files')
        self.assertEqual(report['newly_held'], 1)
        self.assertFalse(report['execution_enabled'])
        ident = report['job_ids'][0]
        restarted = JobStore(self.store.path)
        job = restarted.get(ident)
        self.assertEqual(job['state'], 'HELD')
        self.assertEqual(job['kind'], 'historical_research')
        self.assertIsNone(job['result'])
        self.assertEqual(job['payload']['frozen_request'], self.request)
        self.assertEqual(job['legacy']['source_state'], 'QUEUED_NOT_EXECUTED')
        self.assertEqual(restarted.list_jobs(), [job])
        self.assertIsNone(restarted.claim('worker'))
        self.assertIsNone(restarted.claim('worker', job_id=ident))
        with self.assertRaises(JobStateError):
            restarted.complete(ident, 1, 'worker', {'claim': 'false success'})
        self.assertEqual(import_legacy_queue(restarted, self.repo, source_format='frozen-files')['unchanged'], 1)
        self.assertEqual(len(restarted.events(ident)), 1)
        self.assertEqual((self.repo / 'reports/research_jobs' / (self.request['fingerprint'] + '.json')).read_bytes(),
                         expected_bytes)

    def test_sqlite_dedups_across_formats_and_preserves_latest_observed_state(self):
        enqueue(self.repo, self.request)
        ident = import_legacy_queue(self.store, self.repo, source_format='frozen-files')['job_ids'][0]
        source = DurableResearchState(self.root / 'legacy.sqlite3')
        request_id = source.ingest_record(self.request)
        active = source.claim_next('legacy-worker')
        before = source.status(request_id)
        report = import_legacy_queue(self.store, source.database, source_format='durable-sqlite')
        self.assertEqual(report['job_ids'], [ident])
        self.assertEqual(report['metadata_updated'], 1)
        self.assertEqual(source.status(request_id), before)
        job = self.store.get(ident)
        self.assertEqual(job['legacy']['source_formats'], ['durable-sqlite', 'frozen-files'])
        self.assertEqual(job['legacy']['source_state'], 'RUNNING')
        self.assertEqual(job['legacy']['source_attempt'], active['attempt_no'])
        self.assertEqual(job['legacy']['source_fencing_token'], active['fencing_token'])
        self.assertIsNone(job['worker'])
        self.assertIsNone(job['lease_until'])
        self.assertIsNone(self.store.claim('lab-worker'))
        old = self.root / 'old.sqlite3'
        with closing(sqlite3.connect(source.database)) as src, closing(sqlite3.connect(old)) as dst:
            src.backup(dst)
        source.cancel(request_id)
        source.acknowledge_cancel(request_id, active['attempt_id'], active['fencing_token'], active['worker'])
        self.assertEqual(import_legacy_queue(self.store, source.database, source_format='durable-sqlite')['metadata_updated'], 1)
        self.assertEqual(import_legacy_queue(self.store, old, source_format='durable-sqlite')['unchanged'], 1)
        job = self.store.get(ident)
        self.assertEqual(job['state'], 'HELD')
        self.assertEqual(job['legacy']['source_state'], 'CANCELLED')
        self.assertEqual(len(self.store.list_jobs()), 1)

    def test_corrupt_durable_request_does_not_partially_import_batch(self):
        source = DurableResearchState(self.root / 'legacy.sqlite3')
        source.ingest_record(self.request)
        other = frozen_request(self.repo, 'NRF-FAC-002', 'docs/spec.md',
                               'a'*40, '2020-01-01', '2020-01-31')
        bad_id = source.ingest_record(other)
        with closing(sqlite3.connect(source.database)) as db:
            db.execute("UPDATE jobs SET frozen_json=frozen_json || ' ' WHERE request_id=?", (bad_id,))
            db.commit()
        with self.assertRaisesRegex(ValueError, 'Noncanonical'):
            import_legacy_queue(self.store, source.database, source_format='durable-sqlite')
        self.assertEqual(self.store.list_jobs(), [])

    def test_historical_kind_cannot_enter_runnable_submission(self):
        with self.assertRaises(ValueError):
            self.store.submit('historical_research', {'frozen_request': self.request})
        with self.assertRaises(ValueError):
            import_legacy_queue(self.store, self.store.path, source_format='durable-sqlite')
        self.assertIsNone(self.store.claim('worker'))


if __name__ == '__main__':
    unittest.main()
