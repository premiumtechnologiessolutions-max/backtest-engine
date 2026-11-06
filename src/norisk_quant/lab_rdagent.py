"""Run pinned RD-Agent proposal stages and map only typed local formulas."""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from ._rdagent_probe import MAX_TASKS, SOURCE_TREE_SHA256, digest, validate_reply
from .lab_proposals import SCHEMA as FORMULA_SCHEMA, UPSTREAM_PINS, normalize_proposal_envelope
from .research_evolution import _formula

RDAGENT_REPOSITORY, PINNED_RDAGENT_COMMIT, RDAGENT_LICENSE = UPSTREAM_PINS['rd-agent']
RDAGENT_RUNTIME_SCHEMA = 'NRFX_RDAGENT_FACTOR_PROPOSAL_V1'
RDAGENT_PYTHON_ENV = 'NRFX_RDAGENT_PYTHON'
RDAGENT_CHECKOUT_ENV = 'NRFX_RDAGENT_CHECKOUT'
RDAGENT_MODEL_ENV = 'NRFX_RDAGENT_OLLAMA_MODEL'
RDAGENT_MODEL_DIGEST_ENV = 'NRFX_RDAGENT_OLLAMA_DIGEST'
_EXPERIMENT_CLASS = 'rdagent.scenarios.qlib.experiment.factor_experiment.QlibFactorExperiment'
_MODEL = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,60}(?:/[a-zA-Z0-9][a-zA-Z0-9_.-]{0,60})?'
                    r'(?::[a-zA-Z0-9][a-zA-Z0-9_.-]{0,60})?\Z')
_HEX = re.compile(r'[0-9a-f]{64}\Z')


class RDAgentUnavailable(RuntimeError):
    """The isolated pinned RD-Agent runtime is unconfigured or unavailable."""


class RDAgentRuntimeError(RuntimeError):
    """The bounded official RD-Agent proposal process did not finish."""


def _runtime_configuration():
    python = Path(os.environ.get(RDAGENT_PYTHON_ENV, ''))
    checkout = Path(os.environ.get(RDAGENT_CHECKOUT_ENV, ''))
    model = os.environ.get(RDAGENT_MODEL_ENV, '')
    model_digest = os.environ.get(RDAGENT_MODEL_DIGEST_ENV, '')
    paths_present = (python.is_absolute() and python.is_file()
                     and checkout.is_absolute() and (checkout / 'rdagent').is_dir())
    local_model = (_MODEL.fullmatch(model) and _HEX.fullmatch(model_digest)
                   and 'cloud' not in re.split(r'[/_.:-]+', model.lower()))
    return (python, checkout) if paths_present else None, (model, model_digest) if local_model else None


def _validate_mode(mode):
    if type(mode) is not str or mode not in ('fixture', 'ollama'):
        raise ValueError('RD-Agent proposal mode must be fixture or ollama')


def rdagent_status(mode='fixture') -> dict:
    """Return configuration status without running code or contacting Ollama."""
    _validate_mode(mode)
    paths, local_model = _runtime_configuration()
    configured = paths is not None and (mode == 'fixture' or local_model is not None)
    model, model_digest = local_model if mode == 'ollama' and local_model is not None else (None, None)
    return {
        'engine': 'rd-agent', 'vendor_commit': PINNED_RDAGENT_COMMIT,
        'mode': mode, 'configured': configured, 'available': configured, 'runtime_verified': False,
        'ollama_configured': paths is not None and local_model is not None,
        'model': model, 'model_digest': model_digest,
        'setup': (f'Set {RDAGENT_PYTHON_ENV} and {RDAGENT_CHECKOUT_ENV} to the isolated Python and '
                  f'clean pinned checkout. Ollama mode also requires {RDAGENT_MODEL_ENV} and '
                  f'{RDAGENT_MODEL_DIGEST_ENV}.'),
    }


def _isolated_env(workdir):
    return {
        **{key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR') if key in os.environ},
        'HOME': workdir, 'USERPROFILE': workdir, 'TEMP': workdir, 'TMP': workdir, 'TMPDIR': workdir,
        'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
        'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1',
    }


def _read_native_result(stdout, expected_model_digest):
    try:
        if not 1 <= len(stdout) <= 65_536:
            raise ValueError('Unexpected native result size')
        result = json.loads(stdout)
        if (type(result) is not dict or set(result) != {
                'hypothesis', 'experiment_class', 'tasks', 'provider_calls', 'model_digest'}
                or result['experiment_class'] != _EXPERIMENT_CLASS):
            raise ValueError('Unexpected native result structure')
        if result['model_digest'] != expected_model_digest:
            raise ValueError('Unexpected native model inventory digest')
        validate_reply(result['hypothesis'], 'hypothesis')
        tasks = result['tasks']
        if (type(tasks) is not list or not 1 <= len(tasks) <= MAX_TASKS or any(
                type(task) is not dict or set(task) != {'name', 'description', 'formulation', 'variables'}
                or type(task['name']) is not str for task in tasks)):
            raise ValueError('Unexpected native tasks')
        replies = {task['name']: {k: v for k, v in task.items() if k != 'name'} for task in tasks}
        if len(replies) != len(tasks):
            raise ValueError('Duplicate native task names')
        validate_reply(replies, 'experiment')
        provider_calls = result['provider_calls']
        if (type(provider_calls) is not list or len(provider_calls) != 2 or any(
                type(call) is not dict or set(call) != {'stage', 'prompt_sha256', 'reply_sha256'}
                or call['stage'] != stage or type(call['prompt_sha256']) is not str
                or not _HEX.fullmatch(call['prompt_sha256']) or call['reply_sha256'] != digest(reply)
                for call, stage, reply in zip(provider_calls, ('hypothesis', 'experiment'),
                                              (result['hypothesis'], replies)))):
            raise ValueError('Native proposal receipt did not bind both provider responses')
        return result
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise RDAgentRuntimeError('Invalid pinned RD-Agent proposal receipt') from exc


def _map_tasks(tasks):
    formulas = {}
    mappings = []
    for task in tasks:
        raw = task['variables'].get('nrfx_formula')
        if 'nrfx_formula' not in task['variables']:
            mappings.append({'task': task['name'], 'status': 'NO_TYPED_FORMULA'})
            continue
        try:
            formula = _formula(raw)
        except (ValueError, OverflowError):
            mappings.append({'task': task['name'], 'status': 'INVALID_TYPED_FORMULA'})
            continue
        identity = formula.identity()
        duplicate = identity in formulas
        formulas[identity] = asdict(formula)
        mappings.append({'task': task['name'], 'formula_identity': identity,
                         'status': 'DUPLICATE_TYPED_FORMULA' if duplicate else 'MAPPED_TYPED_FORMULA'})
    if not formulas:
        return None, mappings
    envelope = normalize_proposal_envelope({
        'schema': FORMULA_SCHEMA, 'generator': 'rd-agent', 'source_commit': PINNED_RDAGENT_COMMIT,
        'proposals': list(formulas.values()),
    })
    return envelope, mappings


def run_rdagent_probe(*, seed=0, mode='fixture', progress=lambda stage: None) -> dict:
    """Invoke the official factor proposal stages on a bounded synthetic context."""
    _validate_mode(mode)
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('RD-Agent fixture seed must be an unsigned 32-bit integer')
    paths, local_model = _runtime_configuration()
    if paths is None:
        raise RDAgentUnavailable(f'Configure {RDAGENT_PYTHON_ENV} and {RDAGENT_CHECKOUT_ENV}')
    if mode == 'ollama' and local_model is None:
        raise RDAgentUnavailable(f'Configure a local model and digest in {RDAGENT_MODEL_ENV} and '
                                 f'{RDAGENT_MODEL_DIGEST_ENV}')
    python, checkout = paths
    model, model_digest = local_model if mode == 'ollama' else (None, None)
    child = Path(__file__).with_name('_rdagent_probe.py').resolve()
    stages = ['rdagent_runtime_start', 'rdagent_native_hypothesis', 'rdagent_native_experiment',
              'rdagent_typed_formula_intake']
    progress(stages[0])
    try:
        with tempfile.TemporaryDirectory(prefix='nrfx-rdagent-') as workdir:
            completed = subprocess.run(
                [str(python), '-I', '-B', str(child), str(checkout.resolve()), mode, str(seed),
                 model or '', model_digest or ''],
                cwd=workdir, env=_isolated_env(workdir), stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=25 if mode == 'fixture' else 80,
            )
    except FileNotFoundError as exc:
        raise RDAgentUnavailable('The configured RD-Agent interpreter is unavailable') from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RDAgentRuntimeError('The bounded RD-Agent process failed or timed out') from exc
    if completed.returncode == 2:
        raise RDAgentUnavailable('RD-Agent source failed verification against the pinned package tree')
    if completed.returncode == 3:
        raise RDAgentUnavailable('Install the isolated RD-Agent proposal dependencies')
    if completed.returncode != 0:
        raise RDAgentRuntimeError('RD-Agent did not return a valid native proposal in the selected mode')
    native = _read_native_result(completed.stdout, model_digest)
    progress(stages[1])
    progress(stages[2])
    envelope, mappings = _map_tasks(native['tasks'])
    progress(stages[3])
    report = {
        'schema': RDAGENT_RUNTIME_SCHEMA, 'engine': 'rd-agent', 'mode': mode, 'seed': seed,
        'model': model, 'model_digest': native['model_digest'], 'runtime_executed': True,
        'upstream_runtime_executed': True,
        'model_inference_executed': mode == 'ollama',
        'provider': 'DETERMINISTIC_STRUCTURED_FIXTURE' if mode == 'fixture' else 'OPERATOR_LOOPBACK_OLLAMA',
        'provenance': 'INVENTED_FACTOR_PROPOSAL_FIXTURE' if mode == 'fixture' else 'LOCAL_OLLAMA_SYNTHETIC_CONTEXT',
        'upstream_repository': RDAGENT_REPOSITORY, 'vendor_commit': PINNED_RDAGENT_COMMIT,
        'vendor_license': RDAGENT_LICENSE, 'source_tree_verified': True, 'source_tree_sha256': SOURCE_TREE_SHA256,
        'native': native, 'native_task_count': len(native['tasks']),
        'formula_envelope': envelope, 'formula_mappings': mappings,
        'proposal_binding_sha256': digest({'native': native, 'formula_envelope': envelope}),
        'stages': stages, 'market_data_accessed': False, 'generated_code_executed': False,
        'qlib_backtest_executed': False, 'network_requested': mode == 'ollama',
        'network_scope': 'LOOPBACK_ONLY' if mode == 'ollama' else 'OFFLINE',
        'broker_orders_sent': False, 'live_trading_enabled': False, 'independent_oos_proven': False,
        'status': 'NATIVE_PROPOSAL_ONLY',
    }
    report['deterministic_sha256'] = digest(report)
    return report
