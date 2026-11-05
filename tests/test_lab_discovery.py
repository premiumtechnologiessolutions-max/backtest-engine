import copy
import unittest

import numpy as np
import pandas as pd

from norisk_quant.lab_discovery import diagnose_candidates, generate_specs, signals_for_spec, validate_candidate
from norisk_quant.model import Signal


def fixture():
    index = pd.date_range('2024-01-08', periods=360, freq='min', tz='UTC')
    close = 2000 + 3*np.sin(np.arange(360)/8)
    opening = np.r_[close[0], close[:-1]]
    return pd.DataFrame({'o': opening, 'h': np.maximum(opening, close)+.3,
                         'l': np.minimum(opening, close)-.3, 'c': close}, index=index)


class DiscoveryTests(unittest.TestCase):
    def test_seed_and_generation_are_deterministic(self):
        first = generate_specs(seed=8)
        self.assertEqual(first, generate_specs(seed=8))
        self.assertNotEqual(first, generate_specs(seed=9))
        self.assertEqual({s['family'] for s in first}, {'ema', 'arithmetic'})
        children = generate_specs(seed=8, generation=1, parents=first)
        self.assertEqual(children, generate_specs(seed=8, generation=1, parents=first))
        self.assertTrue(all(s['parent_id'] in {p['id'] for p in first} for s in children))
        self.assertFalse({s['identity'] for s in first} & {s['identity'] for s in children})
        self.assertTrue(all(s['generation'] == 1 for s in children))

    def test_spec_tamper_and_self_supplied_fitness_rejected(self):
        spec = generate_specs()[0]
        bad = copy.deepcopy(spec)
        bad['parameters']['rr'] = 9.
        with self.assertRaises(ValueError):
            validate_candidate(bad)
        bad = dict(spec, accepted=True)
        with self.assertRaises(ValueError):
            validate_candidate(bad)
        with self.assertRaises(ValueError):
            generate_specs(generation=1)

    def test_canonical_signal_dispatch_is_prefix_causal(self):
        minutes = fixture()
        for spec in generate_specs():
            full = signals_for_spec(minutes, spec)
            prefix = signals_for_spec(minutes.iloc[:240], spec)
            self.assertTrue(all(isinstance(signal, Signal) for signal in full))
            boundary = minutes.index[240]
            self.assertEqual([signal for signal in full if signal.confirmed_at <= boundary], prefix)

    def test_feedback_reasons_and_ranked_lineage(self):
        specs = generate_specs()
        records = [{'spec': spec, 'trades': 20, 'net_usd_per_oz': float(index-2),
                    'max_drawdown_usd_per_oz': 4., 'parity_passed': True}
                   for index, spec in enumerate(specs)]
        records[0]['trades'] = 0
        result = diagnose_candidates(records, seed=7)
        self.assertEqual(result, diagnose_candidates(records, seed=7))
        self.assertFalse(result['independent_oos_proven'])
        self.assertFalse(result['strategy_approved'])
        self.assertEqual(result['provenance'], 'SYNTHETIC_NOT_MARKET')
        self.assertIn('NO_EXECUTED_TRADES', result['rankings'][-1]['failure_reasons'])
        self.assertEqual(result['next_generation'], 1)
        self.assertTrue(all(s['parent_id'] in {p['id'] for p in specs} for s in result['proposals']))

    def test_nonfinite_or_unreconciled_feedback_rejected(self):
        spec = generate_specs()[0]
        record = {'spec': spec, 'trades': 1, 'net_usd_per_oz': 1., 'max_drawdown_usd_per_oz': 2.}
        for changed in ({'net_usd_per_oz': float('nan')}, {'curve': [float('inf')]},
                        {'parity_passed': False}, {'max_drawdown_usd_per_oz': -1}, {'accepted': True}):
            with self.assertRaises(ValueError):
                diagnose_candidates([{**record, **changed}])


if __name__ == '__main__':
    unittest.main()
