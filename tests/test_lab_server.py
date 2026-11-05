"""Real HTTP construction checks using a fake, non-executing coordinator."""
import http.client
import json
import threading
import unittest

from norisk_quant.lab_server import MAX_BODY_BYTES, create_server


class FakeCoordinator:
    def __init__(self):
        self.jobs = {}

    def status(self):
        return {"phase": "CONSTRUCTION_SYNTHETIC_ONLY", "market_research_enabled": False}

    def list_jobs(self):
        return list(self.jobs.values())

    def job(self, job_id):
        return self.jobs.get(job_id)

    def submit(self, spec):
        if spec != {"kind": "synthetic_campaign"}:
            raise ValueError("Invalid fixture")
        job = {"id": "abc123", "spec": spec, "status": "QUEUED"}
        self.jobs[job['id']] = job
        return job

    def run_one(self):
        for job in self.jobs.values():
            if job['status'] == 'QUEUED':
                job.update(status='SUCCEEDED', result={"provenance": "SYNTHETIC_NOT_MARKET"})
                return job
        return {"status": "IDLE"}

    def cancel(self, job_id):
        job = self.job(job_id)
        if job:
            job['status'] = 'CANCELLED'
        return job


class LabServerTests(unittest.TestCase):
    def setUp(self):
        self.coordinator = FakeCoordinator()
        self.server = create_server(self.coordinator)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, method, path, body=None, headers=None, authorized=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_address[1], timeout=3)
        supplied = {"Content-Type": "application/json"}
        if authorized:
            supplied.update({"Origin": self.server.url, "X-Lab-Token": self.server.mutation_token})
        supplied.update(headers or {})
        if body is not None and type(body) is not str:
            body = json.dumps(body)
        connection.request(method, path, body=body, headers=supplied)
        response = connection.getresponse()
        data, response_headers, status = response.read(), dict(response.getheaders()), response.status
        connection.close()
        return status, data, response_headers

    def test_loopback_only(self):
        with self.assertRaises(ValueError):
            create_server(self.coordinator, host='0.0.0.0')

    def test_home_has_nonce_and_security_headers(self):
        status, body, headers = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(b'lang="ar" dir="rtl"', body)
        self.assertNotIn(b'__LAB_BOOT__', body)
        self.assertNotIn(b'__LAB_NONCE__', body)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_full_http_cycle(self):
        status, payload, _ = self.request('POST', '/api/jobs', {"kind": "synthetic_campaign"})
        self.assertEqual(status, 201)
        self.assertEqual(json.loads(payload)['id'], 'abc123')
        self.assertEqual(self.request('POST', '/api/worker/tick', {})[0], 200)
        status, payload, _ = self.request('GET', '/api/jobs/abc123')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)['status'], 'SUCCEEDED')
        self.assertEqual(self.request('GET', '/api/jobs/missing')[0], 404)

    def test_requires_origin_and_token(self):
        self.assertEqual(self.request('POST', '/api/jobs', {}, authorized=False)[0], 403)
        self.assertEqual(self.request('POST', '/api/jobs', {}, headers={'Origin': 'http://evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/jobs', {}, headers={'X-Lab-Token': 'wrong'})[0], 403)
        self.assertEqual(self.request('POST', '/api/jobs', {}, headers={'X-Lab-Token': 'é'*32})[0], 403)
        self.assertEqual(self.coordinator.jobs, {})

    def test_dns_rebinding_and_file_routes_rejected(self):
        self.assertEqual(self.request('GET', '/api/status', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('GET', '/../../etc/passwd')[0], 404)
        self.assertEqual(self.request('GET', '/api/jobs/%2e%2e')[0], 400)

    def test_json_shape_size_and_nonfinite_rejected(self):
        self.assertEqual(self.request('POST', '/api/jobs', '{"kind":"synthetic_campaign","kind":"other"}')[0], 400)
        self.assertEqual(self.request('POST', '/api/jobs', '{"value":NaN}')[0], 400)
        self.assertEqual(self.request('POST', '/api/jobs', '[]')[0], 400)
        self.assertEqual(self.request('POST', '/api/jobs', 'x'*(MAX_BODY_BYTES+1))[0], 413)
        self.assertEqual(self.request('POST', '/api/jobs', '{}', headers={'Content-Type':'text/plain'})[0], 415)

    def test_busy_tick_cannot_start_second_worker(self):
        self.server.worker_lock.acquire()
        try:
            status, payload, _ = self.request('POST', '/api/worker/tick', {})
            self.assertEqual(status, 409)
            self.assertEqual(json.loads(payload)['error'], 'worker_busy')
        finally:
            self.server.worker_lock.release()


if __name__ == '__main__':
    unittest.main()
