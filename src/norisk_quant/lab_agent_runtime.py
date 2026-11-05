"""Run exact upstream decision components on canonical invented outcomes."""
from __future__ import annotations

import hashlib
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_file_location
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

_COMPONENTS = {
    'rd-agent': ('rd_agent_bandit.py', 'rdagent/scenarios/qlib/proposal/bandit.py',
                 '5ae609b00426bb10f80e5ecd2398ffbe3c0d001af94d35871f9354f9d6d95536'),
    'tradingagents': ('tradingagents_rating.py', 'tradingagents/agents/rating.py',
                      '90ab5951c3438ba8d9f7536a80c6b5824a6b56ae5cda83f31ada1be311866a52'),
}
_ARM_BY_FAMILY = {'arithmetic': 'factor', 'ema': 'model'}
_FAMILY_BY_ARM = {arm: family for family, arm in _ARM_BY_FAMILY.items()}
_VENDOR_DIR = Path(__file__).resolve().with_name('_agent_upstream')
_MAX_WIRE_BYTES = 8192


class AgentComponentUnavailable(RuntimeError):
    """A fixed upstream component is absent, changed, or unable to run."""


def _source(provider):
    filename, _, expected_sha256 = _COMPONENTS[provider]
    path = _VENDOR_DIR / filename
    try:
        # Git on Windows can check out text with CRLF. Compile the exact pinned
        # Git bytes after canonicalizing only those line endings.
        with path.open('rb') as stream:
            source = stream.read(_MAX_WIRE_BYTES + 1).replace(b'\r\n', b'\n')
    except OSError as exc:
        raise AgentComponentUnavailable('Pinned component source is missing') from exc
    if hashlib.sha256(source).hexdigest() != expected_sha256:
        raise AgentComponentUnavailable('Pinned component source digest differs')
    return path, source


def agent_component_capabilities():
    """Verify the packaged sources without running either component."""
    from .lab_proposals import UPSTREAM_PINS

    result = {}
    for provider, (_, upstream_path, sha256) in _COMPONENTS.items():
        repository, commit, license_id = UPSTREAM_PINS[provider]
        try:
            _source(provider)
        except AgentComponentUnavailable:
            source_verified = False
        else:
            source_verified = True
        result[provider] = {
            'mode': 'pinned_offline_component', 'upstream_repository': repository,
            'upstream_commit': commit, 'upstream_source_path': upstream_path,
            'upstream_license': license_id, 'source_sha256': sha256,
            'source_verified': source_verified, 'llm_workflow_executed': False,
        }
    return result


def _load_pinned(provider):
    path, source = _source(provider)
    name = path.stem

    class VerifiedSourceLoader(SourceFileLoader):
        def get_code(self, fullname):
            # Read the already checked bytes rather than any existing .pyc.
            return self.source_to_code(source, str(path))

    spec = spec_from_file_location(name, path, loader=VerifiedSourceLoader(name, str(path)))
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _child_run():
    """Fixed child entry point. Reads only typed metrics sent by the parent."""
    def guard(event, _args):
        if event.startswith('socket.') or event in {'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'}:
            raise PermissionError('Network and nested process access are disabled for this component')

    sys.addaudithook(guard)
    request = sys.stdin.buffer.read(_MAX_WIRE_BYTES + 1)
    if not 0 < len(request) <= _MAX_WIRE_BYTES:
        raise ValueError('Invalid bounded component payload')
    payload = json.loads(request)
    bandit = _load_pinned('rd-agent')
    rating = _load_pinned('tradingagents')

    # The pinned implementation draws via NumPy's legacy global RNG. This
    # process is private to the job and does not change the worker's RNG state.
    bandit.np.random.seed(payload['seed'])
    controller = bandit.EnvController()
    observations, outcomes = [], []
    for row in payload['feedback']:
        # Only two native slots have a corresponding local diagnostic. Keep
        # all unavailable Qlib statistics at zero, including IC and Sharpe.
        metrics = bandit.Metrics(arr=math.tanh(row['net'] / 10), mdd=math.tanh(row['drawdown'] / 10))
        arm = _ARM_BY_FAMILY[row['family']]
        controller.record(metrics, arm)
        observations.append({'candidate_id': row['id'], 'arm': arm, 'native_arr_slot': metrics.arr,
                             'native_mdd_slot': metrics.mdd, 'reward': controller.reward(metrics)})
        outcomes.append(metrics)

    context = bandit.Metrics(arr=sum(m.arr for m in outcomes) / len(outcomes),
                             mdd=sum(m.mdd for m in outcomes) / len(outcomes))
    selected = controller.decide(context)

    # Translate computed candidate diagnostics to fixture opinions. These
    # labels are authored by NRFX; the upstream parser reconciles them.
    opinions = []
    for family in _ARM_BY_FAMILY:
        rows = [row for row in payload['feedback'] if row['family'] == family]
        net = sum(row['net'] for row in rows)
        direction = 'Buy' if net > 0 else 'Sell' if net < 0 else 'Hold'
        opinions.append(f'{family} fixture rating: {direction}')
    net = sum(row['net'] for row in payload['feedback'])
    drawdown = sum(row['drawdown'] for row in payload['feedback'])
    risk_label = 'Underweight' if drawdown > abs(net) else 'Hold'
    opinions.append(f'drawdown fixture rating: {risk_label}')
    signal = rating.run_rating({'final_trade_decision': '\n'.join(opinions)})
    result = {
        'rd-agent': {'upstream_arm': selected, 'proposal_family': _FAMILY_BY_ARM[selected],
                     'observations': observations},
        'tradingagents': {'fixture_opinions': opinions, 'rating': signal,
                          'review_required': rating.is_review(signal)},
    }
    print(_json(result))


def _native_decisions(seed, feedback):
    request = _json({'seed': seed, 'feedback': feedback})
    env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR') if key in os.environ}
    env.update({'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
    try:
        with tempfile.TemporaryDirectory(prefix='nrfx-agent-') as working_directory:
            process = subprocess.run(
                [sys.executable, '-I', '-B', str(Path(__file__).resolve())], input=request,
                capture_output=True, text=True, encoding='utf-8', cwd=working_directory,
                env=env, timeout=30, check=True,
            )
        if len(process.stdout) > _MAX_WIRE_BYTES:
            raise ValueError('Pinned component output exceeded its contract')
        return json.loads(process.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise AgentComponentUnavailable('Isolated upstream component execution failed') from exc


def decide_agent_components(records, *, seed):
    """Apply the pinned components to the coordinator's reconciled fixture feedback."""
    from .lab_discovery import validate_candidate

    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError('Invalid component seed')
    if type(records) is not list or not 2 <= len(records) <= 16:
        raise ValueError('Agent components require 2..16 canonical candidate records')
    feedback, seen = [], set()
    for record in records:
        if (type(record) is not dict or set(record) != {
                'spec', 'trades', 'net_usd_per_oz', 'max_drawdown_usd_per_oz', 'parity_passed'}
                or record['parity_passed'] is not True):
            raise ValueError('Agent components require reconciled canonical feedback')
        candidate = validate_candidate(record['spec'])
        trades = record['trades']
        net, drawdown = record['net_usd_per_oz'], record['max_drawdown_usd_per_oz']
        if (candidate['id'] in seen or type(trades) is not int or not 0 <= trades <= 100_000
                or type(net) not in (int, float) or not -1e6 <= net <= 1e6
                or type(drawdown) not in (int, float) or not 0 <= drawdown <= 1e6):
            raise ValueError('Invalid or duplicate agent component feedback')
        seen.add(candidate['id'])
        feedback.append({'id': candidate['id'], 'family': candidate['family'], 'trades': trades,
                         'net': float(net), 'drawdown': float(drawdown)})
    if {row['family'] for row in feedback} != set(_ARM_BY_FAMILY):
        raise ValueError('Both candidate families are required for the native bandit')
    feedback.sort(key=lambda row: row['id'])
    capabilities = agent_component_capabilities()
    if any(not info['source_verified'] for info in capabilities.values()):
        raise AgentComponentUnavailable('Pinned agent component source could not be verified')
    decisions = _native_decisions(seed, feedback)
    return {
        'canonical_feedback_sha256': hashlib.sha256(_json(feedback).encode()).hexdigest(),
        'agent_components': {
            provider: {**capabilities[provider], **decisions[provider], 'runtime_executed': True}
            for provider in capabilities
        },
    }


def run_agent_runtime(spec, progress=lambda stage: None):
    """Use offline vendor decisions to drive and reconcile synthetic research."""
    from .execution import run
    from .fast_engine import run_fast
    from .lab_coordinator import _bounded, _frame_digest, _parity, synthetic_fixture
    from .lab_discovery import generate_specs, signals_for_spec
    from .model import Settings

    if type(spec) is not dict or set(spec) - {'kind', 'bars', 'seed', 'code_sha256', 'runtime'}:
        raise ValueError('Agent component jobs accept only synthetic bars and seed')
    bars = _bounded(spec.get('bars', 360), 'bars', 240, 1440)
    seed = _bounded(spec.get('seed', 0), 'seed', 0, 2**32 - 1)
    progress('agent_fixture')
    minutes = synthetic_fixture(bars, seed)
    settings = Settings(ounces=1., roundtrip_cost_per_ounce=.4, max_holding_minutes=60)

    def evaluate(candidate):
        signals = signals_for_spec(minutes, candidate)
        reference = run(minutes, signals, settings)
        fast = run_fast(minutes, signals, settings)
        _parity(reference, fast)
        equity = reference.equity['equity']
        drawdown = float((equity.cummax().clip(lower=0) - equity).clip(lower=0).max())
        return {'id': candidate['id'], 'family': candidate['family'], 'generation': candidate['generation'],
                'parameters': candidate['parameters'], 'trades': len(reference.trades),
                'signals': len(signals), 'net_usd_per_oz': float(equity.iloc[-1]),
                'max_drawdown_usd_per_oz': drawdown, 'parity_passed': True,
                'trade_ledger_sha256': _frame_digest(reference.trades),
                'equity_sha256': _frame_digest(reference.equity)}

    progress('agent_canonical_feedback')
    baselines = generate_specs(seed=seed, generation=0, count=4)
    candidates = [evaluate(candidate) for candidate in baselines]
    evidence_fields = ('trades', 'net_usd_per_oz', 'max_drawdown_usd_per_oz', 'parity_passed')
    feedback = [{'spec': candidate, **{key: row[key] for key in evidence_fields}}
                for candidate, row in zip(baselines, candidates, strict=True)]

    progress('agent_upstream_decisions')
    decisions = decide_agent_components(feedback, seed=seed)
    proposal_family = decisions['agent_components']['rd-agent']['proposal_family']
    parents = [candidate for candidate in baselines if candidate['family'] == proposal_family]
    proposals = generate_specs(seed=seed, generation=1, parents=parents, count=2)

    progress('agent_selected_family_replay')
    candidates.extend(evaluate(candidate) for candidate in proposals)
    return {
        'schema': 'NRFX_SYNTHETIC_AGENT_COMPONENTS_V1', 'provenance': 'SYNTHETIC_NOT_MARKET',
        'bars': bars, 'seed': seed, 'fixture_sha256': _frame_digest(minutes),
        **decisions, 'candidates': candidates, 'next_proposals': proposals,
        'market_data_accessed': False, 'live_trading_enabled': False, 'independent_oos_proven': False,
        'limitations': ['RD-Agent factor means an arithmetic candidate family; model means EMA parameters',
                        'RD-Agent ARR and MDD slots use scaled invented net and drawdown; no annualization',
                        'TradingAgents reconciles locally constructed fixture opinions',
                        'Only the pinned bandit and rating components ran; no LLM agent workflow ran'],
    }


if __name__ == '__main__':
    _child_run()
