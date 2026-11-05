import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from norisk_quant import _tradingagents_worker as worker
from norisk_quant.lab_coordinator import synthetic_fixture
from norisk_quant.lab_tradingagents import (
    TradingAgentsUnavailable, _fixture_sessions, run_tradingagents_graph, tradingagents_status,
)


class TradingAgentsGraphTests(unittest.TestCase):
    def test_fixture_sessions_are_bounded_causal_and_repeatable(self):
        frame = synthetic_fixture(240, 11)
        rows = _fixture_sessions(frame)
        self.assertEqual(rows, _fixture_sessions(synthetic_fixture(240, 11)))
        self.assertNotEqual(rows, _fixture_sessions(synthetic_fixture(240, 12)))
        self.assertEqual(len(rows), 24)
        self.assertEqual(rows[0]['open'], round(float(frame.o.iloc[0]), 6))
        self.assertEqual(rows[-1]['close'], round(float(frame.c.iloc[-1]), 6))
        self.assertTrue(all(row['low'] <= min(row['open'], row['close'])
                            <= max(row['open'], row['close']) <= row['high'] for row in rows))
        self.assertEqual([row['date'] for row in rows], sorted({row['date'] for row in rows}))

    def test_invalid_controls_and_unconfigured_runtime_fail_closed(self):
        with patch.dict(os.environ, {'NRFX_TRADINGAGENTS_PYTHON': '',
                                     'NRFX_TRADINGAGENTS_OLLAMA_MODEL': 'qwen:cloud'}):
            self.assertFalse(tradingagents_status()['installed'])
            self.assertFalse(tradingagents_status()['configured'])
            with self.assertRaisesRegex(TradingAgentsUnavailable, 'Cloud Ollama'):
                run_tradingagents_graph(mode='ollama')
            with self.assertRaises(TradingAgentsUnavailable):
                run_tradingagents_graph()
        for kwargs in ({'bars': 239}, {'bars': 1441}, {'seed': True}, {'mode': 'openai'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                run_tradingagents_graph(**kwargs)

    def test_network_guard_blocks_fixture_and_nonloopback(self):
        code = '''
import runpy
import socket
import sys
namespace = runpy.run_path(sys.argv[1])
namespace['_install_guard'](sys.argv[2])
address = ('127.0.0.1', 11434) if sys.argv[2] == 'fixture' else ('127.0.0.1', 11435)
with socket.socket() as sock:
    try:
        sock.connect(address)
    except PermissionError:
        pass
    else:
        raise RuntimeError('Expected socket connection to be denied before reaching any server')
'''
        for mode in ('fixture', 'ollama'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                subprocess.run([sys.executable, '-I', '-B', '-c', code, worker.__file__, mode],
                               cwd=tmp, check=True, timeout=5, capture_output=True)

    @unittest.skipUnless(os.environ.get('NRFX_REQUIRE_TRADINGAGENTS') == '1'
                         or os.environ.get('NRFX_TRADINGAGENTS_PYTHON'), 'requires pinned TradingAgents venv')
    def test_native_offline_graph_traverses_nodes_and_returns_fixture_ratings(self):
        self.assertTrue(tradingagents_status()['installed'])
        progress = []
        result = run_tradingagents_graph(bars=240, seed=7, progress=progress.append)
        self.assertEqual(result, run_tradingagents_graph(bars=240, seed=7))
        self.assertEqual(result['upstream_commit'], worker.PIN)
        self.assertEqual(result['executed_nodes'], list(worker.GRAPH_NODES))
        self.assertEqual(result['fixture_tools_executed'], ['get_stock_data', 'get_verified_market_snapshot'])
        self.assertIn(result['fixture_sha256'], result['reports']['market_report'])
        self.assertIn('Fixture debate remains balanced.', result['reports']['investment_plan'])
        self.assertIn('FINAL TRANSACTION PROPOSAL: **HOLD**', result['reports']['trader_investment_plan'])
        self.assertEqual(result['final_rating'], 'Hold')
        self.assertEqual(result['model_provider'], 'fixed_fixture_responses')
        self.assertTrue(result['official_graph_executed'])
        self.assertFalse(result['model_inference_executed'])
        self.assertFalse(result['market_data_accessed'])
        self.assertFalse(result['live_trading_enabled'])
        self.assertEqual(progress, ['tradingagents_fixture', 'tradingagents_official_graph'])


if __name__ == '__main__':
    unittest.main()
