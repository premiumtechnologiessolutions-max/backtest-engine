"""Synthetic metadata-only checks: no market or vendor execution."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest

from norisk_quant.lab_jobs import JobStateError, JobStore


class JobTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "jobs.sqlite3"
        self.now = 1000.
        self.store = JobStore(self.path, clock=lambda: self.now)

    def tearDown(self):
        self.directory.cleanup()

    def test_dedup_restart_and_immutable_result(self):
        job = self.store.submit("quantum", {"b": 2, "a": 1})
        repeated = self.store.submit("quantum", {"a": 1, "b": 2})
        self.assertEqual(job["id"], repeated["id"])
        claim = self.store.claim("worker")
        done = self.store.complete(job["id"], claim["token"], "worker", {"objective": -3})
        self.assertEqual(done["state"], "SUCCEEDED")
        restarted = JobStore(self.path, clock=lambda: self.now)
        self.assertEqual(restarted.get(job["id"])["result"], {"objective": -3})
        self.assertEqual(restarted.submit("quantum", {"a": 1, "b": 2})["state"], "SUCCEEDED")
        with self.assertRaises(JobStateError):
            self.store.complete(job["id"], claim["token"], "worker", {"objective": 999})
        self.assertEqual(self.store.get(job["id"])["result"], {"objective": -3})

    def test_expiry_reclaim_fences_late_worker(self):
        job = self.store.submit("synthetic_campaign", {"seed": 7})
        first = self.store.claim("first", 5)
        self.now += 5
        with self.assertRaises(JobStateError):
            self.store.complete(job["id"], first["token"], "first", {"result": 1})
        self.assertEqual(self.store.recover_expired(), 1)
        second = self.store.claim("second", 5)
        self.assertGreater(second["token"], first["token"])
        self.assertEqual(second["attempt"], 2)
        with self.assertRaises(JobStateError):
            self.store.heartbeat(job["id"], first["token"], "first")
        self.store.complete(job["id"], second["token"], "second", {"result": 2})
        self.assertEqual(self.store.get(job["id"])["result"], {"result": 2})
        self.assertEqual([x["reason"] for x in self.store.events(job["id"])],
                         ["submitted", "claimed", "lease_expired", "claimed", "completed"])

    def test_running_cancel_invalidates_completion(self):
        job = self.store.submit("quantum", {"seed": 9})
        claim = self.store.claim("worker")
        cancelled = self.store.cancel(job["id"])
        self.assertEqual(cancelled["state"], "CANCELLED")
        with self.assertRaises(JobStateError):
            self.store.complete(job["id"], claim["token"], "worker", {"late": True})
        self.assertIsNone(self.store.claim("other"))
        self.assertIsNone(self.store.get(job["id"])["result"])

    def test_failure_and_queued_cancel(self):
        first = self.store.submit("synthetic_campaign", {"id": 1})
        claim = self.store.claim("worker")
        failed = self.store.fail(first["id"], claim["token"], "worker", "synthetic failure")
        self.assertEqual(failed["state"], "FAILED")
        self.assertIsNone(failed["result"])
        second = self.store.submit("synthetic_campaign", {"id": 2})
        self.assertEqual(self.store.cancel(second["id"])["state"], "CANCELLED")
        self.assertIsNone(self.store.claim("worker"))

    def test_specific_claim_leaves_other_queued_jobs_untouched(self):
        older = self.store.submit("synthetic_campaign", {"seed": 1})
        self.now += 1
        target = self.store.submit("synthetic_campaign", {"seed": 2})
        self.assertIsNone(self.store.claim("worker", job_id="f"*64))
        with self.assertRaises(ValueError):
            self.store.claim("worker", job_id="not-a-job-id")
        self.assertEqual(self.store.claim("worker", job_id=target["id"])["id"], target["id"])
        self.assertEqual(self.store.get(older["id"])["state"], "QUEUED")
        self.assertIsNone(self.store.claim("worker", job_id=target["id"]))
        self.assertEqual(self.store.claim("worker")["id"], older["id"])

    def test_heartbeat_extends_and_requires_owner(self):
        job = self.store.submit("quantum", {})
        claim = self.store.claim("worker", 5)
        self.now += 4
        with self.assertRaises(JobStateError):
            self.store.heartbeat(job["id"], claim["token"], "intruder")
        self.store.heartbeat(job["id"], claim["token"], "worker", 5)
        self.now += 4
        self.assertEqual(self.store.recover_expired(), 0)
        self.store.complete(job["id"], claim["token"], "worker", {"ok": True})

    def test_progress_is_fenced_durable_and_extends_lease(self):
        job = self.store.submit("synthetic_campaign", {"seed": 5})
        first = self.store.claim("first", 5)
        self.now += 4
        value = self.store.progress(job["id"], first["token"], "first", "quantum_optimize", 6)
        self.assertEqual(value["lease_until"], self.now + 6)
        restarted = JobStore(self.path, clock=lambda: self.now)
        self.assertEqual(restarted.events(job["id"])[-1]["reason"], "stage:quantum_optimize")
        with self.assertRaises(ValueError):
            self.store.progress(job["id"], first["token"], "first", "arbitrary stage / path")
        self.now += 6
        second = self.store.claim("second", 5)
        with self.assertRaises(JobStateError):
            self.store.progress(job["id"], first["token"], "first", "late_stage")
        self.assertEqual(self.store.get(job["id"])["token"], second["token"])
        self.assertNotIn("stage:late_stage", [e["reason"] for e in self.store.events(job["id"])])

    def test_simultaneous_claim_has_one_owner(self):
        self.store.submit("quantum", {"seed": 1})
        def claim(index):
            return JobStore(self.path, clock=lambda: self.now).claim(f"worker-{index}")
        with ThreadPoolExecutor(max_workers=8) as pool:
            values = list(pool.map(claim, range(8)))
        self.assertEqual(sum(value is not None for value in values), 1)

    def test_invalid_spec_and_result_are_not_published(self):
        for payload in ({"value": float("nan")}, {1: "ambiguous"}, {"huge": "x"*1_000_001}):
            with self.assertRaises(ValueError):
                self.store.submit("quantum", payload)
        job = self.store.submit("quantum", {})
        claim = self.store.claim("worker")
        with self.assertRaises(ValueError):
            self.store.complete(job["id"], claim["token"], "worker", {"invalid": float("inf")})
        self.assertEqual(self.store.get(job["id"])["state"], "RUNNING")
        self.assertIsNone(self.store.get(job["id"])["result"])


if __name__ == "__main__":
    unittest.main()
