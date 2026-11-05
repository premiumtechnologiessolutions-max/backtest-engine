"""Run bounded synthetic and Quantum jobs through the local durable queue."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import hashlib
import sys
from importlib import import_module, metadata, util
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
from .quantum_backends import (BackendUnavailable, backend_capabilities,
                               opencl_device_identity, solve_problem, validate_opencl_selector)
from .quantum_optimizer import BinaryProblem
from .quantum_selection import compile_selection
from .strategy import ema_cross_signals

_VENDORS = {
    'nautilus_synthetic': 'nautilus',
    'lean_synthetic': 'lean',
    'finrl_synthetic': 'finrl',
    'finrl_training_synthetic': 'finrl',
}
_AGENT_WORKFLOWS = {
    'tradingagents_graph_synthetic': ('tradingagents', 'run_tradingagents_graph'),
    'rdagent_factor_synthetic': ('rdagent', 'run_rdagent_probe'),
}
_BACKENDS = {'numpy', 'pennylane', 'opencl', 'opencl-cpu'}
_OPENCL = {'opencl', 'opencl-cpu'}
_LEASE_SECONDS = 120


def code_identity() -> str:
    digest = hashlib.sha256()
    root = Path(__file__).parent
    for path in sorted(p for p in root.rglob('*') if p.is_file() and p.suffix in {'.py', '.html'}):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b'\0')
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def runtime_identity():
    result = {'numpy': np.__version__, 'pandas': pd.__version__, 'python': sys.version}
    for package in ('pennylane', 'pennylane-lightning', 'nautilus_trader',
                    'pyopencl', 'gymnasium', 'matplotlib', 'stable-baselines3', 'torch'):
        try:
            result[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            result[package] = None
    return result


def _job_runtime(payload):
    result = runtime_identity()
    backend = payload.get('backend')
    if backend in _OPENCL:
        try:
            result['opencl_device'] = opencl_device_identity(backend, payload.get('device'))
        except BackendUnavailable:
            result['opencl_device'] = None
    vendor = _VENDORS.get(payload['kind'])
    if vendor in {'lean', 'finrl'}:
        module = import_module(f'.lab_{vendor}', __package__)
        result[vendor] = getattr(module, f'{vendor}_status')()
    if payload['kind'] in _AGENT_WORKFLOWS:
        result['agent_workflow'] = _agent_workflow_status(payload['kind'], payload['mode'])
    return result


def _agent_workflow_status(kind, mode='fixture'):
    name, _ = _AGENT_WORKFLOWS[kind]
    module = import_module(f'.lab_{name}', __package__)
    return getattr(module, f'{name}_status')(mode=mode)


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
    supported = {'synthetic_campaign', 'synthetic_discovery', 'quantum_optimization',
                 'synthetic_external_proposals', 'synthetic_agent_components', *_VENDORS,
                 *_AGENT_WORKFLOWS}
    if type(kind) is not str or kind not in supported:
        raise ValueError('Only construction synthetic jobs and supplied binary problems are enabled')
    if kind in _AGENT_WORKFLOWS:
        allowed = {'kind', 'seed', 'mode'}
        if kind == 'tradingagents_graph_synthetic':
            allowed.add('bars')
        mode = spec.get('mode', 'fixture')
        if set(spec) - allowed or type(mode) is not str or mode not in {'fixture', 'ollama'}:
            raise ValueError('Agent workflows accept only synthetic controls and fixture or ollama mode')
        normalized = {'kind': kind, 'mode': mode, 'seed': _bounded(spec.get('seed', 0), 'seed', 0, 2**32-1)}
        if 'bars' in allowed:
            normalized['bars'] = _bounded(spec.get('bars', 360), 'bars', 240, 1440)
        return normalized
    if kind in _VENDORS:
        if set(spec) - {'kind', 'bars', 'seed'}:
            raise ValueError('External synthetic jobs accept only bars and seed')
        max_bars = 480 if kind == 'finrl_training_synthetic' else 1000
        return {'kind':kind, 'bars':_bounded(spec.get('bars',240),'bars',60,max_bars),
                'seed':_bounded(spec.get('seed',0),'seed',0,2**32-1)}
    if kind == 'synthetic_agent_components':
        if set(spec) - {'kind', 'bars', 'seed'}:
            raise ValueError('Native component jobs accept only bars and seed')
        return {'kind': kind, 'bars': _bounded(spec.get('bars', 360), 'bars', 240, 1440),
                'seed': _bounded(spec.get('seed', 0), 'seed', 0, 2**32-1)}
    if kind == 'synthetic_external_proposals':
        from .lab_proposals import normalize_proposal_envelope
        if set(spec) - {'kind', 'bars', 'seed', 'envelope'}:
            raise ValueError('Invalid external proposal job fields')
        return {'kind': kind, 'bars': _bounded(spec.get('bars', 360), 'bars', 240, 1440),
                'seed': _bounded(spec.get('seed', 0), 'seed', 0, 2**32-1),
                'envelope': normalize_proposal_envelope(spec.get('envelope'))}
    common = {'kind', 'seed', 'layers', 'evaluations', 'backend', 'device'}
    allowed = common | ({'problem'} if kind == 'quantum_optimization' else {'bars', 'select_count'})
    if set(spec) - allowed:
        raise ValueError('Unknown job fields; market paths and execution commands are not accepted')
    normalized = dict(kind=kind, seed=_bounded(spec.get('seed',0),'seed',0,2**32-1),
                      layers=_bounded(spec.get('layers',1),'layers',1,3),
                      evaluations=_bounded(spec.get('evaluations',32),'evaluations',1,256),
                      backend=spec.get('backend','numpy'))
    backend = normalized['backend']
    if type(backend) is not str or backend not in _BACKENDS:
        raise ValueError('Unsupported backend')
    if backend in _OPENCL:
        normalized['device'] = validate_opencl_selector(spec.get('device'))
    elif 'device' in spec:
        raise ValueError('Device selection requires an OpenCL backend')
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


def _run_agent_workflow(kind, payload, progress):
    name, handler = _AGENT_WORKFLOWS[kind]
    module = import_module(f'.lab_{name}', __package__)
    options = {key: payload[key] for key in ('seed', 'mode', 'bars') if key in payload}
    progress(kind)
    result = getattr(module, handler)(**options, progress=progress)
    if (result.get('mode') != payload['mode'] or result.get('runtime_executed') is not True
            or result.get('model_inference_executed') is not (payload['mode'] == 'ollama')
            or result.get('market_data_accessed') is not False
            or result.get('live_trading_enabled') is not False):
        raise ValueError('Native agent workflow receipt failed its synthetic execution contract')
    if kind == 'rdagent_factor_synthetic' and result.get('formula_envelope') is not None:
        from .lab_proposals import normalize_proposal_envelope, run_proposal_campaign
        envelope = normalize_proposal_envelope(result['formula_envelope'])
        if envelope['generator'] != 'rd-agent':
            raise ValueError('Native RD-Agent returned a proposal for a different generator')
        # The allowlisted typed proposal enters the same canonical parity gate
        # as imported formulas. It cannot supply executable code or market data.
        evaluation = run_proposal_campaign({
            'envelope': envelope, 'seed': payload['seed'] ^ 0x6E2563C1,
        }, progress)
        result['canonical_evaluation'] = evaluation
        result['candidates'] = evaluation['candidates']
    return result


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
                              evaluations=spec['evaluations'], seed=spec['seed'], device=spec.get('device'))
    stages += ['selection_compilation', 'quantum_selection', 'complete']
    return {'schema': 'NRFX_UNIFIED_SYNTHETIC_CAMPAIGN_V1',
            'provenance': 'SYNTHETIC_NOT_MARKET', 'fixture_sha256': fixture_id,
            'bars': len(minutes), 'cost_per_ounce': .4,
            'market_data_accessed': False, 'live_trading_enabled': False,
            'candidates': summaries, 'compilation': compilation.manifest,
            'selection': selection, 'stages': stages,
            'limitations': ['Fixture performance is not market performance',
                            'Candidate curves use independent accounts, not a shared-capacity portfolio',
                            'Selection uses the same synthetic fixture; no out-of-sample evidence']}


class LabCoordinator:
    def __init__(self, database):
        self.store = JobStore(database)
        self.worker = 'local-' + uuid.uuid4().hex
        self._lock = threading.Lock()

    def status(self):
        jobs = self.store.list_jobs(1000)
        counts = Counter(j['state'] for j in jobs)
        current_code = code_identity()
        vendors = {}
        for vendor in dict.fromkeys(_VENDORS.values()):
            kind = f'{vendor}_synthetic'
            if vendor == 'nautilus':
                from .lab_nautilus import PINNED_NAUTILUS_VERSION
                available = {'installed': util.find_spec('nautilus_trader') is not None,
                             'required_version': PINNED_NAUTILUS_VERSION}
            else:
                module = import_module(f'.lab_{vendor}', __package__)
                available = getattr(module, f'{vendor}_status')()
            identity = _job_runtime({'kind': kind})
            receipts = [j['result'] for j in jobs if _VENDORS.get(j['kind']) == vendor
                        and j['state'] == 'SUCCEEDED'
                        and (j['result'] or {}).get('runtime_executed') is True
                        and (j['result'] or {}).get('code_sha256') == current_code
                        and j['payload'].get('runtime') == identity]
            vendors[vendor] = {**available, 'execution_verified': bool(receipts), 'mode': 'synthetic_only'}
            if vendor == 'finrl':
                vendors[vendor]['training_verified'] = any(r.get('rl_training_executed') is True for r in receipts)
        from .lab_agent_runtime import agent_component_capabilities
        quantum = backend_capabilities()
        devices = quantum['backends']['opencl']['devices']
        runtime = runtime_identity()
        observed = [j for j in jobs if j['state'] == 'SUCCEEDED'
                    and (j['result'] or {}).get('code_sha256') == current_code]
        for provider, info in agent_component_capabilities().items():
            verified = any(j['result'].get('agent_components', {}).get(provider, {}).get('runtime_executed')
                           for j in observed)
            vendors[provider] = {**info, 'execution_verified': bool(verified)}
        for kind in _AGENT_WORKFLOWS:
            available = _agent_workflow_status(kind)
            completed = [j for j in observed if j['kind'] == kind and j['result'].get('runtime_executed') is True]
            mode_status = {'fixture': available}
            if available.get('ollama_configured') and any(j['payload'].get('mode') == 'ollama' for j in completed):
                mode_status['ollama'] = _agent_workflow_status(kind, 'ollama')
            receipts = [j['result'] for j in completed if j['payload'].get('mode') in mode_status
                        and j['payload'].get('runtime') == {
                            **runtime, 'agent_workflow': mode_status[j['payload']['mode']]}]
            vendors[kind] = {**available, 'execution_verified': bool(receipts),
                             'fixture_execution_verified': any(r.get('mode') == 'fixture' for r in receipts),
                             'model_inference_verified': any(r.get('model_inference_executed') is True
                                                             for r in receipts)}
        for job in observed:
            if job['payload'].get('backend') != 'opencl':
                continue
            selection = job['result'].get('selection', job['result'])
            bound_runtime = job['payload'].get('runtime', {})
            if (selection.get('gpu_used') is True and selection.get('opencl_device') in devices
                    and selection.get('opencl_numpy_parity')
                    and all(bound_runtime.get(key) == value for key, value in runtime.items())):
                quantum['gpu'].update(compatibility='VERIFIED', execution_verified=True)
                break
        return {'phase': 'CONSTRUCTION_SYNTHETIC_ONLY', 'market_research_enabled': False,
                'quantum': quantum, 'jobs': dict(counts),
                'code_sha256': current_code, 'engine_complete': False,
                'integration': 'discovery_canonical_multiasset_portfolio_quantum_local_ui',
                'external_engines': vendors}

    def submit(self, spec):
        payload = validate_spec(spec)
        payload['code_sha256'] = code_identity()
        payload['runtime'] = _job_runtime(payload)
        return self.store.submit(payload['kind'], payload)

    def list_jobs(self):
        return self.store.list_jobs()

    def job(self, job_id):
        result = self.store.get(job_id)
        result['events'] = self.store.events(job_id)
        return result

    def cancel(self, job_id):
        return self.store.cancel(job_id)

    @contextmanager
    def _renew_while_running(self, job_id, token):
        stop = threading.Event()

        def renew():
            while not stop.wait(_LEASE_SECONDS / 4):
                try:
                    self.store.heartbeat(job_id, token, self.worker, _LEASE_SECONDS)
                except JobStateError:
                    return

        thread = threading.Thread(target=renew, name='lab-lease', daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join()

    def run_one(self, *, job_id=None):
        if not self._lock.acquire(blocking=False):
            raise ValueError('A local worker is already running')
        try:
            claimed = self.store.claim(self.worker, lease_seconds=_LEASE_SECONDS, job_id=job_id)
            if claimed is None:
                return {'state': 'IDLE'}
            ident, token = claimed['id'], claimed['token']
            payload = claimed['payload']
            def progress(stage):
                self.store.progress(ident, token, self.worker, stage, lease_seconds=_LEASE_SECONDS)
            try:
                if payload['code_sha256'] != code_identity():
                    raise ValueError('Code changed since submission; submit a fresh job')
                if payload['runtime'] != _job_runtime(payload):
                    raise ValueError('Runtime changed since submission')
                with self._renew_while_running(ident, token):
                    result = self._execute(claimed['kind'], payload, progress)
                if payload.get('backend') in _OPENCL:
                    selection = result.get('selection', result)
                    if selection.get('opencl_device') != payload['runtime']['opencl_device']:
                        raise ValueError('OpenCL device changed during execution')
                if claimed['kind'] == 'lean_synthetic':
                    if result.get('runtime_image_id') != payload['runtime']['lean']['runtime_image_id']:
                        raise ValueError('LEAN image changed during execution')
                if claimed['kind'] in _AGENT_WORKFLOWS:
                    current = _agent_workflow_status(claimed['kind'], payload['mode'])
                    if payload['runtime']['agent_workflow'] != current:
                        raise ValueError('Agent runtime changed during execution')
                if payload['code_sha256'] != code_identity():
                    raise ValueError('Code changed during execution')
                progress('publish')
                result['code_sha256'] = payload['code_sha256']
                return self.store.complete(ident, token, self.worker, result)
            except JobStateError:
                return self.store.get(ident)
            except Exception as exc:
                safe_error = (f'{type(exc).__name__}: check the optional runtime and configuration'
                              if type(exc).__name__ in {'NautilusUnavailable', 'BackendUnavailable',
                                                       'LeanUnavailable', 'FinRLUnavailable',
                                                       'AgentComponentUnavailable', 'TradingAgentsUnavailable',
                                                       'RDAgentUnavailable'}
                              else f'{type(exc).__name__}: local execution failed; no result accepted')
                # Keep paths, tokens and arbitrary external messages out of UI.
                try:
                    return self.store.fail(ident, token, self.worker, safe_error)
                except JobStateError:
                    return self.store.get(ident)
        finally:
            self._lock.release()

    @staticmethod
    def _execute(kind, payload, progress):
        if kind == 'synthetic_campaign':
            return run_synthetic_campaign(payload, progress)
        if kind == 'synthetic_discovery':
            from .lab_campaigns import run_discovery_campaign
            return run_discovery_campaign(payload, progress)
        if kind == 'synthetic_external_proposals':
            from .lab_proposals import run_proposal_campaign
            return run_proposal_campaign(payload, progress)
        if kind == 'synthetic_agent_components':
            from .lab_agent_runtime import run_agent_runtime
            return run_agent_runtime(payload, progress)
        if kind in _AGENT_WORKFLOWS:
            return _run_agent_workflow(kind, payload, progress)
        if kind in _VENDORS:
            vendor = _VENDORS[kind]
            progress(kind)
            module = import_module(f'.lab_{vendor}', __package__)
            return getattr(module, f'run_{kind}')(bars=payload['bars'], seed=payload['seed'])
        if kind == 'quantum_optimization':
            progress('quantum_selection')
            return solve_problem(BinaryProblem.from_dict(payload['problem']),
                backend=payload['backend'], layers=payload['layers'],
                evaluations=payload['evaluations'], seed=payload['seed'], device=payload.get('device'))
        raise ValueError('Unknown local job handler')
