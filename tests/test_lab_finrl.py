import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from norisk_quant.lab_finrl import (
    FinRLUnavailable, PINNED_FINRL_COMMIT, PINNED_FINRL_SOURCE_SHA256,
    _SOURCE_FILE, finrl_status, run_finrl_synthetic,
)


class FinRLAdapterTests(unittest.TestCase):
    def test_rejects_unbounded_input_before_loading(self):
        with patch('norisk_quant.lab_finrl._load_environment', side_effect=AssertionError):
            for bars, seed in ((39, 0), (2001, 0), (60, -1), (60, 2**32), (60, True), (60.0, 0)):
                with self.subTest(bars=bars, seed=seed), self.assertRaises(ValueError):
                    run_finrl_synthetic(bars, seed)

    def test_unconfigured_and_tampered_source_are_unavailable(self):
        with patch.dict(os.environ, {'NRFX_FINRL_SOURCE': ''}):
            self.assertFalse(finrl_status()['source_verified'])
            with self.assertRaises(FinRLUnavailable):
                run_finrl_synthetic(40)
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {'NRFX_FINRL_SOURCE': root}):
            source = Path(root) / _SOURCE_FILE
            source.parent.mkdir(parents=True)
            source.write_text('raise AssertionError("must never execute modified code")')
            with self.assertRaisesRegex(FinRLUnavailable, 'differs from the pinned revision'):
                run_finrl_synthetic(40)

    @unittest.skipUnless(
        os.environ.get('NRFX_REQUIRE_FINRL') == '1' or (
            os.environ.get('NRFX_FINRL_SOURCE') and importlib.util.find_spec('stable_baselines3')
        ), 'requires the optional pinned FinRL environment')
    def test_real_finrl_fills_and_account_values(self):
        self.assertTrue(finrl_status()['source_verified'])
        first = run_finrl_synthetic(60, 7)
        second = run_finrl_synthetic(60, 7)
        self.assertTrue(first['runtime_executed'])
        self.assertEqual(first['engine_version'], PINNED_FINRL_COMMIT)
        self.assertEqual(first['source_sha256'], PINNED_FINRL_SOURCE_SHA256)
        self.assertEqual(first['deterministic_sha256'], second['deterministic_sha256'])
        self.assertEqual(len(first['native_account_value']), 60)
        self.assertEqual(len(first['native_share_changes']), 59)
        self.assertEqual(first['native_share_changes'][0], [4, 2])
        self.assertEqual(first['native_share_changes'][2], [-4, -2])
        self.assertGreater(first['fee_cost'], 0)
        self.assertEqual(first['final_holdings'], [0, 0])
        self.assertFalse(first['market_data_accessed'])
        self.assertFalse(first['rl_training_executed'])
