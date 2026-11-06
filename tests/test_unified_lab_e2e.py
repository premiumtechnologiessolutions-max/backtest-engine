"""Real HTTP -> persistent coordinator -> canonical replay -> QAOA fixture path."""
from __future__ import annotations

import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from norisk_quant.lab_coordinator import LabCoordinator
from norisk_quant.lab_server import create_server


class UnifiedLabHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / 'lab.sqlite3'
        self.lab = LabCoordinator(self.database)
        self.server = create_server(self.lab, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()

    def request(self, method, path, payload=None, *, authenticated=True):
        headers = {}
        body = None
        if method == 'POST':
            body = json.dumps(payload if payload is not None else {})
            headers['Content-Type'] = 'application/json'
            if authenticated:
                headers['Origin'] = self.server.url
                headers['X-Lab-Token'] = self.server.mutation_token
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=30)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read()
            if response.getheader('Content-Type', '').startswith('application/json'):
                data = json.loads(data)
            return response.status, data
        finally:
            connection.close()

    def test_http_campaign_replays_and_survives_coordinator_restart(self):
        status, initial = self.request('GET', '/api/status')
        self.assertEqual(status, 200)
        self.assertFalse(initial['market_research_enabled'])
        self.assertFalse(initial['engine_complete'])
        status, html = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(b'X-Lab-Token', html)
        for kind in ('tradingagents_graph_synthetic', 'rdagent_factor_synthetic'):
            self.assertIn(kind, initial['external_engines'])
            self.assertFalse(initial['external_engines'][kind]['execution_verified'])
            self.assertFalse(initial['external_engines'][kind]['model_inference_verified'])
            self.assertIn(kind.encode(), html)

        spec = {'kind': 'synthetic_campaign', 'bars': 240, 'evaluations': 8, 'seed': 17}
        status, queued = self.request('POST', '/api/jobs', spec)
        self.assertEqual(status, 201)
        self.assertEqual(queued['state'], 'QUEUED')
        status, completed = self.request('POST', '/api/worker/tick')
        self.assertEqual(status, 200)
        self.assertEqual(completed['state'], 'SUCCEEDED', completed.get('error'))
        result = completed['result']
        self.assertEqual(result['provenance'], 'SYNTHETIC_NOT_MARKET')
        self.assertFalse(result['market_data_accessed'])
        self.assertEqual(len(result['candidates']), 4)
        self.assertTrue(all(candidate['parity_passed'] for candidate in result['candidates']))
        self.assertTrue(all(candidate['trades'] > 0 for candidate in result['candidates']))
        self.assertEqual(len(result['selection']['selected']), 2)
        self.assertGreaterEqual(result['selection']['objective_gap'], 0)
        self.assertFalse(result['selection']['quantum_hardware_used'])
        self.assertFalse(result['selection']['quantum_advantage_proven'])
        self.assertIn('quantum_selection', result['stages'])
        self.assertEqual(result['code_sha256'], queued['payload']['code_sha256'])

        status, detailed = self.request('GET', '/api/jobs/' + queued['id'])
        self.assertEqual(status, 200)
        self.assertEqual(detailed['result'], result)
        self.assertTrue(detailed['events'])
        status, reused = self.request('POST', '/api/jobs', spec)
        self.assertEqual(status, 201)
        self.assertEqual(reused['id'], queued['id'])
        self.assertEqual(reused['attempt'], 1)
        restarted = LabCoordinator(self.database)
        self.assertEqual(restarted.job(queued['id'])['result'], result)
        self.assertEqual(restarted.run_one()['state'], 'IDLE')

    def test_http_rejects_unauthorized_and_market_input_and_cancels(self):
        status, _ = self.request('POST', '/api/jobs', {'kind': 'synthetic_campaign'}, authenticated=False)
        self.assertEqual(status, 403)
        status, _ = self.request('POST', '/api/jobs', {'kind': 'synthetic_campaign', 'gold_zip': '/private/Gold.zip'})
        self.assertEqual(status, 400)
        self.assertEqual(self.lab.list_jobs(), [])
        status, queued = self.request('POST', '/api/jobs', {'kind': 'synthetic_campaign', 'seed': 18})
        self.assertEqual(status, 201)
        status, cancelled = self.request('POST', '/api/jobs/' + queued['id'] + '/cancel')
        self.assertEqual(status, 200)
        self.assertEqual(cancelled['state'], 'CANCELLED')
        status, idle = self.request('POST', '/api/worker/tick')
        self.assertEqual(status, 200)
        self.assertEqual(idle['state'], 'IDLE')
        self.assertIsNone(self.lab.job(queued['id'])['result'])

    def test_starting_a_selected_job_keeps_older_job_queued(self):
        older = self.lab.submit({'kind': 'synthetic_campaign', 'seed': 20})
        chosen = self.lab.submit({'kind': 'synthetic_campaign', 'seed': 21,
                                  'bars': 240, 'evaluations': 1})
        status, completed = self.request('POST', '/api/worker/tick', {'job_id': chosen['id']})
        self.assertEqual(status, 200)
        self.assertEqual(completed['id'], chosen['id'])
        self.assertEqual(completed['state'], 'SUCCEEDED')
        self.assertEqual(self.lab.job(older['id'])['state'], 'QUEUED')


if __name__ == '__main__':
    unittest.main()
