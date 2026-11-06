import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from norisk_quant import lab_lean as lean


class LeanSyntheticTests(unittest.TestCase):
    def test_fixture_is_bounded_deterministic_and_uses_native_quote_layout(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            first, second = root / 'first', root / 'second'
            self.assertEqual(lean._fixture(first, 1450, 8), lean._fixture(second, 1450, 8))
            directory = first / 'forex/oanda/minute/eurusd'
            with zipfile.ZipFile(directory / '20200107_quote.zip') as archive:
                lines = archive.read('20200107_eurusd_minute_quote.csv').decode().splitlines()
        self.assertEqual(len(lines), 10)
        self.assertEqual(len(lines[0].split(',')), 11)
        self.assertTrue(lines[0].startswith('0,'))
        self.assertFalse(lean._configuration(1450)['environments']['backtesting']['live-mode'])

    def test_runtime_refuses_unconfigured_image_and_invalid_fixture(self):
        with patch.dict(os.environ, {lean.LEAN_IMAGE_ENV: ''}):
            with self.assertRaises(lean.LeanUnavailable):
                lean.run_lean_synthetic()
        with self.assertRaises(ValueError):
            lean.run_lean_synthetic(bars=2001)

    def test_native_lifecycle_rejects_fabricated_success_without_closed_trades(self):
        report = {'runtimeStatistics': {'NRFX Synthetic Bars': '40'}, 'orders': {},
                  'totalPerformance': {'closedTrades': []}}
        with self.assertRaises(lean.LeanRuntimeError):
            lean._native_lifecycle(report, [], 40)

    def test_runtime_command_has_no_network_or_host_data_mount(self):
        image = 'sha256:' + '1' * 64
        with tempfile.TemporaryDirectory() as scratch:
            fixture, results = Path(scratch) / 'fixture', Path(scratch) / 'results'
            args = lean._container_command('docker', image, 'nrfx-test', fixture, results)
        self.assertEqual(args[-1], image)
        self.assertTrue({'--network=none', '--pull=never', '--read-only', '--cap-drop=ALL'} <= set(args))
        mounts = [args[i + 1] for i, part in enumerate(args) if part == '--mount']
        self.assertEqual(mounts, [f'type=bind,source={fixture},target=/fixture,readonly',
                                  f'type=bind,source={results},target=/results'])

    def require_native_runtime(self):
        if os.getenv('NRFX_REQUIRE_LEAN') != '1' and not lean.lean_status()['available']:
            self.skipTest('optional native LEAN image is not configured')

    def test_native_lean_integration(self):
        self.require_native_runtime()
        result = lean.run_lean_synthetic(bars=40, seed=7)
        self.assertTrue(result['runtime_executed'])
        self.assertEqual(result['vendor_commit'], lean.PINNED_LEAN_COMMIT)
        self.assertEqual(result['bars_observed_by_strategy'], 40)
        self.assertEqual(result['orders_count'], 4)
        self.assertEqual(result['fills_count'], 4)
        self.assertEqual(result['closed_positions_count'], 2)
        self.assertFalse(result['market_data_accessed'])
        self.assertFalse(result['canonical_execution_parity_verified'])

    def test_native_lean_durable_dispatch(self):
        self.require_native_runtime()
        from norisk_quant.lab_coordinator import LabCoordinator

        with tempfile.TemporaryDirectory() as scratch:
            coordinator = LabCoordinator(Path(scratch) / 'jobs.sqlite')
            job = coordinator.submit({'kind': 'lean_synthetic', 'bars': 60, 'seed': 7})
            completed = coordinator.run_one(job_id=job['id'])
            self.assertEqual(completed['state'], 'SUCCEEDED', completed)
            self.assertEqual(completed['result']['closed_positions_count'], 3)
            self.assertEqual(completed['result']['runtime_image_id'], os.environ[lean.LEAN_IMAGE_ENV])
            self.assertEqual(coordinator.job(job['id'])['result'], completed['result'])
