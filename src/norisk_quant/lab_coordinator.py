"""One executable construction path: durable jobs -> canonical engines -> QAOA.

Only deterministic invented OHLC and explicit bounded binary problems are
accepted. No path, broker credential, provider runner or market input is accepted.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import sys
from importlib import metadata, util
from pathlib import Path
import threading
import uuid

import numpy as np
import pandas as pd

from .execution import run
from .fast_engine import run_fast
from .lab_jobs import JobStateError, JobStore
from .math_discovery import Formula, arithmetic_signals
from .model import Settings
from .quantum_backends import backend_capabilities, solve_problem
from .quantum_optimizer import BinaryProblem
from .quantum_selection import compile_selection
from .strategy import ema_cross_signals


def code_identity() -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in Path(__file__).parent.iterdir() if p.suffix in {'.py', '.html'}):
        digest.update(path.name.encode())
        digest.update(b'\0')
        digest.update(path.read_bytes())
    return digest.hexdigest()


def runtime_identity():
    result = {'numpy': np.__version__, 'pandas': pd.__version__, 'python': sys.version}
    for package in ('pennylane', 'nautilus_trader'):
        try:
            result[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            result[package] = None
    return result


def synthetic_fixture(bars=720, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(bars)
    close = 2000 + 4 * np.sin(t * 2 * np.pi / 65) + .002 * t + rng.normal(0, .06, bars)
    opening = np.r_[close[0], close[:-1]]
    return pd.DataFrame({'o': opening, 'h': np.maximum(opening, close) + .3,
                         'l': np.minimum(opening, close) - .3, 'c': close},
                        index=pd.date_range('2024-01-08', periods=bars, freq='min', tz='UTC'))


def _bounded(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be integer {minimum}..{maximum}')
    return value


def validate_spec(spec):
    if type(spec) is not dict:
        raise ValueError('Job specification must be an object')
    kind = spec.get('kind')
    supported = {'synthetic_campaign', 'synthetic_discovery', 'quantum_optimization', 'nautilus_synthetic'}
    if kind not in supported:
        raise ValueError('Only construction synthetic jobs and supplied binary problems are enabled')
    if kind == 'nautilus_synthetic':
        if set(spec) - {'kind', 'bars', 'seed'}:
            raise ValueError('External synthetic jobs accept only bars and seed')
        return {'kind':kind, 'bars':_bounded(spec.get('bars',240),'bars',60,1000),
                'seed':_bounded(spec.get('seed',0),'seed',0,2**32-1)}
    common = {'kind', 'seed', 'layers', 'evaluations', 'backend'}
    allowed = common | ({'problem'} if kind == 'quantum_optimization' else {'bars', 'select_count'})
    if set(spec) - allowed:
        raise ValueError('Unknown job fields; market paths and execution commands are not accepted')
    normalized = dict(kind=kind, seed=_bounded(spec.get('seed',0),'seed',0,2**32-1),
                      layers=_bounded(spec.get('layers',1),'layers',1,3),
                      evaluations=_bounded(spec.get('evaluations',32),'evaluations',1,256),
                      backend=spec.get('backend','numpy'))
    if normalized['backend'] not in {'numpy','pennylane'}:
        raise ValueError('Unsupported backend')
    if kind == 'synthetic_campaign':
        normalized['bars'] = _bounded(spec.get('bars',720),'bars',240,3000)
        normalized['select_count'] = _bounded(spec.get('select_count',2),'select_count',1,4)
    elif kind == 'synthetic_discovery':
        normalized['bars'] = _bounded(spec.get('bars',360),'bars',240,1440)
        normalized['select_count'] = _bounded(spec.get('select_count',4),'select_count',1,4)
        # Sixteen-variable simulation is substantially larger than the old demo.
        normalized['evaluations'] = _bounded(spec.get('evaluations',8),'evaluations',1,32)
        normalized['layers'] = _bounded(spec.get('layers',1),'layers',1,2)
    else:
        problem = BinaryProblem.from_dict(spec.get('problem'))
        if len(problem.labels) > 10:
            raise ValueError('Interactive jobs support at most 10 binary variables')
        normalized['problem'] = problem.payload()
    return normalized


def _frame_digest(frame):
    return hashlib.sha256(frame.to_csv(index=True, float_format='%.17g').encode()).hexdigest()


def _parity(reference, fast):
    for field in ('trades', 'equity'):
        pd.testing.assert_frame_equal(getattr(reference, field), getattr(fast, field),
                                      check_dtype=False, check_exact=False, atol=1e-8, rtol=0)
    for field in ('pending_at_end', 'expired_signals', 'uncertain_entry_tp_deferred'):
        if getattr(reference, field) != getattr(fast, field):
            raise ValueError(f'Canonical reference/fast parity failed: {field}')


def run_synthetic_campaign(spec, progress=lambda stage: None):
    """Exercise existing engines; fixture results are never market evidence."""
    progress('synthetic_data')
    minutes = synthetic_fixture(spec['bars'], spec['seed'])
    fixture_id = _frame_digest(minutes)
    settings = Settings(ounces=1., roundtrip_cost_per_ounce=.4, max_holding_minutes=60)
    variants = [('ema_5_15', {'fast': 5, 'slow': 15}),
                ('ema_9_25', {'fast': 9, 'slow': 25}),
                ('formula_forward', 0), ('formula_reverse', 1)]
    candidates, increments, summaries, stages = [], [], [], ['synthetic_data']
    for ident, params in variants:
        progress('canonical_' + ident)
        if isinstance(params, dict):
            signals = ema_cross_signals(minutes, timeframe='M1', atr_period=8,
                                        stop_atr=1.5, rr=1.5, **params)
        else:
            formula = Formula(lookback=12, feature_a=0, feature_b=2, feature_c=1,
                              operator_ab=0, operator_c=0, reverse=params,
                              threshold=.3, stop_usd=1.5, reward_risk=1.5, cooldown=8)
            signals = arithmetic_signals(minutes, formula)
        signals = list(signals)
        reference = run(minutes, signals, settings)
        fast = run_fast(minutes, signals, settings)
        _parity(reference, fast)
        equity = reference.equity['equity']
        changes = equity.diff()
        changes.iloc[0] = equity.iloc[0]
        increments.append(changes.to_numpy())
        candidates.append({'id': ident, 'expected_return': float(changes.mean()), 'source_id': fixture_id})
        peak = equity.cummax().clip(lower=0)
        summaries.append({'id': ident, 'signals': len(signals), 'trades': len(reference.trades),
                          'net_usd_per_oz': float(equity.iloc[-1]),
                          'max_drawdown_usd_per_oz': float((peak-equity).clip(lower=0).max()),
                          'parity_passed': True, 'trade_ledger_sha256': _frame_digest(reference.trades),
                          'equity_sha256': _frame_digest(reference.equity),
                          'parameters': params if isinstance(params, dict) else {'reverse': params},
                          'curve': [float(x) for x in equity.iloc[::max(1,len(equity)//80)]]})
        stages.append('canonical_' + ident)
    progress('selection_compilation')
    covariance = np.cov(np.asarray(increments), ddof=1)
    compilation = compile_selection(candidates, covariance.tolist(), spec['select_count'],
                                    provenance='synthetic', source_ids=(fixture_id,))
    progress('quantum_selection')
    selection = solve_problem(compilation.problem, backend=spec['backend'], layers=spec['layers'],
                              evaluations=spec['evaluations'], seed=spec['seed'])
    stages += ['selection_compilation', 'quantum_selection', 'complete']
    return {'schema': 'NRFX_UNIFIED_SYNTHETIC_CAMPAIGN_V1',
            'provenance': 'SYNTHETIC_NOT_MARKET', 'fixture_sha256': fixture_id,
            'bars': len(minutes), 'cost_per_ounce': .4,
            'market_data_accessed': False, 'live_trading_enabled': False,
            'candidates': summaries, 'compilation': compilation.manifest,
            'selection': selection, 'stages': stages,
            'limitations': ['Fixture performance is not market performance',
                            'Candidate curves use independent accounts, not a shared-capacity portfolio',
                            'Selection uses the same synthetic fixture; no out-of-sample evidence',
                            'GPU and external market engines are not executed']}


class LabCoordinator:
    def __init__(self, database):
        self.store = JobStore(database)
        self.worker = 'local-' + uuid.uuid4().hex
        self._lock = threading.Lock()

    def status(self):
        counts = Counter(j['state'] for j in self.store.list_jobs(1000))
        return {'phase': 'CONSTRUCTION_SYNTHETIC_ONLY', 'market_research_enabled': False,
                'quantum': backend_capabilities(), 'jobs': dict(counts),
                'code_sha256': code_identity(), 'engine_complete': False,
                'integration': 'discovery_canonical_multiasset_portfolio_quantum_local_ui',
                'external_engines': {'nautilus': {'installed': util.find_spec('nautilus_trader') is not None,
                    'required_version':'1.221.0','execution_verified':False,'mode':'synthetic_only'}}}

    def submit(self, spec):
        payload = validate_spec(spec)
        payload['code_sha256'] = code_identity()
        payload['runtime'] = runtime_identity()
        return self.store.submit(payload['kind'], payload)

    def list_jobs(self):
        return self.store.list_jobs()

    def job(self, job_id):
        result = self.store.get(job_id)
        result['events'] = self.store.events(job_id)
        return result

    def cancel(self, job_id):
        return self.store.cancel(job_id)

    def run_one(self):
        if not self._lock.acquire(blocking=False):
            raise ValueError('A local worker is already running')
        try:
            claimed = self.store.claim(self.worker, lease_seconds=120)
            if claimed is None:
                return {'state': 'IDLE'}
            ident, token = claimed['id'], claimed['token']
            payload = claimed['payload']
            def progress(stage):
                self.store.progress(ident, token, self.worker, stage, lease_seconds=120)
            try:
                if payload['code_sha256'] != code_identity():
                    raise ValueError('Code changed since submission; submit a fresh job')
                if payload['runtime'] != runtime_identity():
                    raise ValueError('Runtime changed since submission')
                if claimed['kind'] == 'synthetic_campaign':
                    result = run_synthetic_campaign(payload, progress)
                elif claimed['kind'] == 'synthetic_discovery':
                    from .lab_campaigns import run_discovery_campaign
                    result = run_discovery_campaign(payload, progress)
                elif claimed['kind'] == 'nautilus_synthetic':
                    progress('nautilus_synthetic')
                    from .lab_nautilus import run_nautilus_synthetic
                    result = run_nautilus_synthetic(bars=payload['bars'],seed=payload['seed'])
                elif claimed['kind'] == 'quantum_optimization':
                    progress('quantum_selection')
                    result = solve_problem(BinaryProblem.from_dict(payload['problem']),
                        backend=payload['backend'], layers=payload['layers'],
                        evaluations=payload['evaluations'], seed=payload['seed'])
                else:
                    raise ValueError('Unknown local job handler')
                if payload['code_sha256'] != code_identity():
                    raise ValueError('Code changed during execution')
                progress('publish')
                result['code_sha256'] = payload['code_sha256']
                return self.store.complete(ident, token, self.worker, result)
            except JobStateError:
                return self.store.get(ident)
            except Exception as exc:
                safe_error = (f'{type(exc).__name__}: install the matching optional engine extra'
                              if type(exc).__name__ in {'NautilusUnavailable', 'BackendUnavailable'}
                              else f'{type(exc).__name__}: local execution failed; no result accepted')
                # Keep paths, tokens and arbitrary external messages out of UI.
                try:
                    return self.store.fail(ident, token, self.worker, safe_error)
                except JobStateError:
                    return self.store.get(ident)
        finally:
            self._lock.release()
