"""Run a bounded synthetic fixture through the pinned native LEAN launcher."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
import zipfile

from norisk_quant.upstream_trade_normalizers import PINNED_VENDOR

PINNED_LEAN_COMMIT = PINNED_VENDOR['lean']
LEAN_IMAGE_ENV = 'NRFX_LEAN_RUNTIME_IMAGE'
LEAN_RUNTIME_SCHEMA = 'NRFX_LEAN_SYNTHETIC_RUNTIME_V1'
ALGORITHM_ID = 'nrfx-lean-synthetic'
SYMBOL = 'EURUSD'
_IMAGE_ID = re.compile(r'sha256:[0-9a-f]{64}\Z')
_TIMEOUT = 120
_LABELS = {
    'org.opencontainers.image.source': 'https://github.com/QuantConnect/Lean',
    'org.opencontainers.image.revision': PINNED_LEAN_COMMIT,
    'org.noriskfx.contract': LEAN_RUNTIME_SCHEMA,
}


class LeanUnavailable(RuntimeError):
    """A locally prepared, matching LEAN runtime is unavailable."""


class LeanRuntimeError(RuntimeError):
    """The native launcher or native lifecycle verification failed."""


def lean_status() -> dict:
    image = os.environ.get(LEAN_IMAGE_ENV, '')
    docker = shutil.which('docker') is not None
    configured = bool(_IMAGE_ID.fullmatch(image))
    return {
        'engine': 'lean', 'vendor_commit': PINNED_LEAN_COMMIT,
        'configured': configured, 'docker_client_available': docker,
        'runtime_image_id': image if configured else None,
        'available': configured and docker, 'runtime_verified': False,
        'setup': f'Build the pinned source image and set {LEAN_IMAGE_ENV} to its local image ID.',
    }


def _validate(bars: int, seed: int) -> None:
    if type(bars) is not int or not 40 <= bars <= 2000:
        raise ValueError('Synthetic LEAN fixture requires 40..2000 bars')
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('Synthetic fixture seed must be an unsigned 32-bit integer')


def _configuration(bars: int) -> dict:
    engine = 'QuantConnect.Lean.Engine.'
    return {
        'environment': 'backtesting',
        'algorithm-type-name': 'NrfxSyntheticAlgorithm',
        'algorithm-language': 'CSharp',
        'algorithm-location': '/runner/QuantConnect.Algorithm.CSharp.dll',
        'algorithm-id': ALGORITHM_ID,
        'backtest-name': ALGORITHM_ID,
        'composer-dll-directory': '/runner',
        'data-folder': '/tmp/data',
        'results-destination-folder': '/results',
        'log-handler': 'QuantConnect.Logging.ConsoleLogHandler',
        'messaging-handler': 'QuantConnect.Messaging.Messaging',
        'job-queue-handler': 'QuantConnect.Queues.JobQueue',
        'api-handler': 'QuantConnect.Api.Api',
        'job-user-id': 0,
        'api-access-token': '',
        'job-organization-id': '',
        'force-exchange-always-open': True,
        'data-provider': engine + 'DataFeeds.DefaultDataProvider',
        'map-file-provider': 'QuantConnect.Data.Auxiliary.LocalDiskMapFileProvider',
        'factor-file-provider': 'QuantConnect.Data.Auxiliary.LocalDiskFactorFileProvider',
        'object-store': engine + 'Storage.LocalObjectStore',
        'parameters': {'bars': str(bars)},
        'environments': {'backtesting': {
            'live-mode': False,
            'setup-handler': engine + 'Setup.BacktestingSetupHandler',
            'result-handler': engine + 'Results.BacktestingResultHandler',
            'data-feed-handler': engine + 'DataFeeds.FileSystemDataFeed',
            'real-time-handler': engine + 'RealTime.BacktestingRealTimeHandler',
            'history-provider': [engine + 'HistoricalData.SubscriptionDataReaderHistoryProvider'],
            'transaction-handler': engine + 'TransactionHandlers.BacktestingTransactionHandler',
        }},
    }


def _fixture(root: Path, bars: int, seed: int) -> str:
    rng = random.Random(seed)
    day = datetime(2020, 1, 6)
    bid = 110000
    rows_by_day: dict[str, list[str]] = {}
    for offset in range(bars):
        moment = day + timedelta(minutes=offset)
        opened = bid
        bid += rng.randrange(-5, 6)
        prices = [opened, max(opened, bid) + 3, min(opened, bid) - 3, bid]
        quote = [f'{price / 100000:.5f}' for price in prices] + ['1000000']
        quote += [f'{(price + 10) / 100000:.5f}' for price in prices] + ['1000000']
        row = ','.join([str(offset % 1440 * 60000), *quote])
        rows_by_day.setdefault(moment.strftime('%Y%m%d'), []).append(row)
    destination = root / 'forex/oanda/minute/eurusd'
    destination.mkdir(parents=True)
    digest = hashlib.sha256()
    for date, rows in rows_by_day.items():
        payload = ('\n'.join(rows) + '\n').encode('ascii')
        digest.update(date.encode('ascii') + b'\0' + payload)
        with zipfile.ZipFile(destination / f'{date}_quote.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f'{date}_eurusd_minute_quote.csv', payload)
    (root / 'config.json').write_text(json.dumps(_configuration(bars)), encoding='utf-8')
    return digest.hexdigest()


def _runtime_image() -> tuple[str, str]:
    docker = shutil.which('docker')
    image = os.environ.get(LEAN_IMAGE_ENV, '')
    if docker is None or not _IMAGE_ID.fullmatch(image):
        raise LeanUnavailable(f'Docker and a local immutable image ID in {LEAN_IMAGE_ENV} are required')
    try:
        result = subprocess.run(
            [docker, 'image', 'inspect', '--format', '{{json .}}', image],
            capture_output=True, timeout=15, check=True, text=True, encoding='utf-8',
        )
        observed = json.loads(result.stdout)
        labels = observed['Config']['Labels']
        if observed['Id'] != image or any(labels.get(k) != v for k, v in _LABELS.items()):
            raise LeanUnavailable('Local image does not identify the pinned LEAN harness')
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise LeanUnavailable('Unable to verify the pinned local LEAN image') from exc
    return docker, image


def _container_command(docker: str, image: str, name: str, fixture: Path, results: Path) -> list[str]:
    if ',' in str(fixture) or ',' in str(results):
        raise LeanUnavailable('LEAN temporary directory paths may not contain commas')
    uid = os.getuid() if hasattr(os, 'getuid') else 65532
    gid = os.getgid() if hasattr(os, 'getgid') else 65532
    if uid == 0:
        uid = gid = 65532
    return [
        docker, 'run', '--rm', '--pull=never', '--name', name, '--network=none',
        '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
        '--user', f'{uid}:{gid}', '--memory=2048m', '--cpus=2', '--pids-limit=128',
        '--log-driver=none', '--tmpfs', '/tmp:rw,nosuid,nodev,size=192m,mode=1777',
        '--env', 'HOME=/tmp', '--env', 'DOTNET_EnableDiagnostics=0',
        '--env', 'DOTNET_CLI_TELEMETRY_OPTOUT=1', '--workdir', '/tmp',
        '--mount', f'type=bind,source={fixture},target=/fixture,readonly',
        '--mount', f'type=bind,source={results},target=/results', image,
    ]


def _json(path: Path, limit: int) -> object:
    def reject_constant(value: str):
        raise ValueError(f'Unexpected JSON constant {value}')

    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= limit:
            raise ValueError('Invalid native result file')
        return json.loads(path.read_text(encoding='utf-8'), parse_float=Decimal,
                          parse_constant=reject_constant)
    except (OSError, ValueError, UnicodeError) as exc:
        raise LeanRuntimeError(f'Invalid or missing native LEAN file {path.name}') from exc


def _decimal(value: object) -> Decimal:
    if type(value) not in (int, str, Decimal):
        raise ValueError('Invalid native decimal')
    number = Decimal(value)
    if not number.is_finite() or abs(number) > 10**12:
        raise ValueError('Out-of-range native decimal')
    return number


def _time(value: object) -> Decimal:
    if type(value) is str and 'T' in value:
        moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return Decimal(str(moment.timestamp()))
    return _decimal(value)


def _native_lifecycle(report: object, order_events: object, bars: int) -> dict:
    expected_pairs = (bars - 12) // 20 + 1
    try:
        if not isinstance(report, dict) or not isinstance(order_events, list):
            raise ValueError('Unexpected native result structure')
        if len(order_events) > expected_pairs * 16:
            raise ValueError('Unexpected native order event count')
        observed = int(report['runtimeStatistics']['NRFX Synthetic Bars'])
        orders = report['orders']
        trades = report['totalPerformance']['closedTrades']
        if observed != bars or len(orders) != 2 * expected_pairs or len(trades) != expected_pairs:
            raise ValueError('Native quote/order/closure counts differ from fixed algorithm')
        fills = []
        ids = set()
        for event in order_events:
            if event['algorithmId'] != ALGORITHM_ID or event['symbolValue'] != SYMBOL:
                raise ValueError('Unexpected native event identity')
            status = event['status'].casefold()
            if status in ('invalid', 'canceled', 'cancelled', 'partiallyfilled'):
                raise ValueError('Unexpected incomplete native order')
            if status != 'filled':
                continue
            order_id = event['orderId']
            if type(order_id) is not int or order_id <= 0 or order_id in ids or str(order_id) not in orders:
                raise ValueError('Unmatched native filled order')
            ids.add(order_id)
            quantity, price, stamp = map(_decimal, (event['fillQuantity'], event['fillPrice'], event['time']))
            if price <= 0 or quantity != (1000 if len(fills) % 2 == 0 else -1000):
                raise ValueError('Unexpected native signed fill')
            if fills and stamp < _decimal(fills[-1]['time']):
                raise ValueError('Native fill chronology mismatch')
            fills.append({'order_id': order_id, 'time': str(stamp), 'quantity': str(quantity),
                          'price': str(price), 'currency': event['fillPriceCurrency'],
                          'fee': str(_decimal(event.get('orderFeeAmount', 0)))})
        if len(fills) != 2 * expected_pairs:
            raise ValueError('Missing native filled orders')
        closures = []
        for index, trade in enumerate(trades):
            entry, exit = fills[index * 2:index * 2 + 2]
            if (_decimal(trade['entryPrice']) != _decimal(entry['price'])
                    or _decimal(trade['exitPrice']) != _decimal(exit['price'])
                    or _time(trade['entryTime']) != _decimal(entry['time'])
                    or _time(trade['exitTime']) != _decimal(exit['time'])
                    or _decimal(trade['quantity']) != 1000):
                raise ValueError('Native closed trade does not reconcile with its fills')
            closures.append({'entry_order_id': entry['order_id'], 'exit_order_id': exit['order_id'],
                             'profit_loss': str(_decimal(trade['profitLoss'])),
                             'total_fees': str(_decimal(trade['totalFees']))})
        return {'bars_observed_by_strategy': observed, 'orders_count': len(orders),
                'fills_count': len(fills), 'closed_positions_count': len(closures),
                'native_fills': fills, 'native_closed_trades': closures}
    except (ValueError, KeyError, TypeError, AttributeError, InvalidOperation, OverflowError) as exc:
        raise LeanRuntimeError('Native LEAN order, fill and closure validation failed') from exc


def run_lean_synthetic(bars: int = 240, seed: int = 0) -> dict:
    """Execute the pinned native launcher in a network-isolated local container."""
    _validate(bars, seed)
    docker, image = _runtime_image()
    name = f'nrfx-lean-{uuid.uuid4().hex}'
    with tempfile.TemporaryDirectory(prefix='nrfx-lean-') as directory:
        scratch = Path(directory).resolve()
        fixture = scratch / 'fixture'
        results = scratch / 'results'
        fixture.mkdir()
        results.mkdir(mode=0o777)
        # Bind-mounted results are writable by the unprivileged container user.
        # The host parent is private and never mounted.
        results.chmod(0o777)
        fixture_digest = _fixture(fixture, bars, seed)
        command = _container_command(docker, image, name, fixture, results)
        log = scratch / 'launcher.log'
        try:
            with log.open('wb') as output:
                completed = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT,
                                           timeout=_TIMEOUT, check=False)
            if completed.returncode:
                with log.open('rb') as output:
                    output.seek(max(0, log.stat().st_size - 2500))
                    tail = output.read(2500).decode('utf-8', errors='replace').strip()
                raise LeanRuntimeError(f'Native LEAN exited with {completed.returncode}: {tail}')
        except subprocess.TimeoutExpired as exc:
            try:
                subprocess.run([docker, 'rm', '--force', name], capture_output=True, timeout=10, check=False)
            except (OSError, subprocess.SubprocessError):
                pass
            raise LeanRuntimeError('Native LEAN exceeded the bounded runtime') from exc
        except OSError as exc:
            raise LeanRuntimeError('Unable to start local LEAN container') from exc
        lifecycle = _native_lifecycle(
            _json(results / f'{ALGORITHM_ID}.json', 8 * 1024 * 1024),
            _json(results / f'{ALGORITHM_ID}-order-events.json', 2 * 1024 * 1024), bars,
        )
    result = {
        'schema': LEAN_RUNTIME_SCHEMA, 'engine': 'lean', 'vendor_commit': PINNED_LEAN_COMMIT,
        'runtime_executed': True, 'fixture': 'INVENTED_EURUSD_M1_BIDASK', 'seed': seed,
        'bars_per_side': bars, 'fixture_sha256': fixture_digest, **lifecycle,
        'cost_model': 'VENDOR_DEFAULT_FX_FIXTURE_FEES_NOT_CANONICAL_XAUUSD',
        'canonical_execution_parity_verified': False, 'market_data_accessed': False,
        'network_requested': False, 'broker_orders_sent': False, 'profitability_claimed': False,
    }
    result['deterministic_sha256'] = hashlib.sha256(json.dumps(
        result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    result['runtime_image_id'] = image
    return result
