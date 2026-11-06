import importlib.util
import unittest
from unittest.mock import patch

from norisk_quant.lab_nautilus import (
    NautilusUnavailable, PINNED_NAUTILUS_VERSION, _fixture, run_nautilus_synthetic,
)


class NautilusAdapterTests(unittest.TestCase):
    def test_invalid_fixture_rejected_before_vendor_import(self):
        with patch('norisk_quant.lab_nautilus.importlib.util.find_spec', side_effect=AssertionError):
            for bars, seed in ((True, 0), (39, 0), (2001, 0), (40, True), (40, -1)):
                with self.assertRaises(ValueError):
                    run_nautilus_synthetic(bars, seed)

    def test_missing_vendor_explicit(self):
        with patch('norisk_quant.lab_nautilus.importlib.util.find_spec', return_value=None):
            with self.assertRaises(NautilusUnavailable):
                run_nautilus_synthetic(40)

    def test_fixture_spread_geometry_and_seed(self):
        bid, ask = _fixture(40, 2)
        self.assertTrue(bid.equals(_fixture(40, 2)[0]))
        self.assertFalse(bid.equals(_fixture(40, 3)[0]))
        self.assertTrue((bid['high'] >= bid[['open', 'close']].max(axis=1)).all())
        self.assertTrue((bid['low'] <= bid[['open', 'close']].min(axis=1)).all())
        self.assertTrue(((ask['close'] - bid['close'] - .0001).abs() < 1e-12).all())

    @unittest.skipUnless(importlib.util.find_spec('nautilus_trader'), 'optional NautilusTrader is not installed')
    def test_real_vendor_engine_fills_and_determinism(self):
        first = run_nautilus_synthetic(60, 7)
        second = run_nautilus_synthetic(60, 7)
        self.assertEqual(first['engine_version'], PINNED_NAUTILUS_VERSION)
        self.assertEqual(first['deterministic_sha256'], second['deterministic_sha256'])
        self.assertEqual(first['bars_observed_by_strategy'], 60)
        self.assertGreater(first['orders_count'], 0)
        self.assertGreater(first['fills_count'], 0)
        self.assertGreater(first['closed_positions_count'], 0)
        self.assertEqual(first['rejected_or_denied_orders'], 0)
        self.assertEqual(first['native_fill_report_rows'], first['fills_count'])
        self.assertFalse(first['market_data_accessed'])
        self.assertFalse(first['canonical_execution_parity_verified'])
