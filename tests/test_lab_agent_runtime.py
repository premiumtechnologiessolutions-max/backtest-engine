from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from norisk_quant import lab_agent_runtime
from norisk_quant.lab_discovery import generate_specs, validate_candidate


class AgentComponentTests(unittest.TestCase):
    def test_real_upstream_decisions_drive_children_and_reconcile_fixture_opinions(self):
        rng_before = np.random.get_state()
        stages = []
        result = lab_agent_runtime.run_agent_runtime({'bars': 240, 'seed': 0}, stages.append)
        rng_after = np.random.get_state()
        np.testing.assert_array_equal(rng_before[1], rng_after[1])
        self.assertEqual(rng_before[2:], rng_after[2:])

        components = result['agent_components']
        self.assertTrue(all(c['runtime_executed'] and c['source_verified'] for c in components.values()))
        self.assertTrue(all(not c['llm_workflow_executed'] for c in components.values()))
        candidates = result['candidates']
        self.assertEqual(len(candidates), 6)
        self.assertTrue(all(c['parity_passed'] and c['trades'] > 0 for c in candidates))
        rd = components['rd-agent']
        self.assertEqual({row['arm'] for row in rd['observations']}, {'factor', 'model'})
        self.assertEqual({row['candidate_id'] for row in rd['observations']}, {c['id'] for c in candidates[:4]})
        for child in result['next_proposals']:
            self.assertEqual(validate_candidate(child)['family'], rd['proposal_family'])
            self.assertIn(child['id'], {row['id'] for row in candidates[4:]})

        ta = components['tradingagents']
        self.assertIn('arithmetic fixture rating: Sell', ta['fixture_opinions'])
        self.assertIn('ema fixture rating: Buy', ta['fixture_opinions'])
        self.assertEqual(ta['rating'], 'REVIEW')
        self.assertIs(ta['review_required'], True)
        self.assertFalse(result['market_data_accessed'])
        self.assertFalse(result['live_trading_enabled'])
        self.assertEqual(stages[-2:], ['agent_upstream_decisions', 'agent_selected_family_replay'])
        self.assertEqual(result, lab_agent_runtime.run_agent_runtime({'bars': 240, 'seed': 0}))

    def test_modified_upstream_source_and_unreconciled_feedback_fail_closed(self):
        records = [{'spec': spec, 'trades': 1, 'net_usd_per_oz': 1.,
                    'max_drawdown_usd_per_oz': 1., 'parity_passed': True}
                   for spec in generate_specs(seed=1, count=2)]
        bad = [dict(records[0], parity_passed=False), records[1]]
        with self.assertRaisesRegex(ValueError, 'reconciled canonical feedback'):
            lab_agent_runtime.decide_agent_components(bad, seed=1)
        with self.assertRaises(ValueError):
            lab_agent_runtime.run_agent_runtime({'market_path': '/outside-lab/quotes.parquet'})
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(lab_agent_runtime, '_VENDOR_DIR', Path(tmp)):
                (Path(tmp) / 'rd_agent_bandit.py').write_text('raise RuntimeError("changed")\n')
                self.assertFalse(lab_agent_runtime.agent_component_capabilities()['rd-agent']['source_verified'])
                with self.assertRaisesRegex(lab_agent_runtime.AgentComponentUnavailable, 'could not be verified'):
                    lab_agent_runtime.decide_agent_components(records, seed=1)


if __name__ == '__main__':
    unittest.main()
