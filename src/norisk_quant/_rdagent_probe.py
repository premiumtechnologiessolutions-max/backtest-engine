"""Isolated child process for the pinned RD-Agent factor proposal scenario."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
from http.client import HTTPConnection
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import sys
from unittest.mock import patch


# The bytes of each of these 694 paths were checked against the Git blobs at
# microsoft/RD-Agent 484776c211e4fbbeef03e0ec00d6bbee7362a4f4 before hashing.
SOURCE_TREE_SHA256 = '00b44cef90f4c213d9fe5c18933eca2fe3d01d26ebb13780f81fddf5d4f26921'
SOURCE_FILE_COUNT = 694
OLLAMA_ADDRESS = ('127.0.0.1', 11434)
MAX_REPLY_BYTES = 16_384
MAX_TASKS = 4
_HEX = re.compile(r'[0-9a-f]{64}\Z')
HYPOTHESIS_FIELDS = (
    'hypothesis', 'reason', 'concise_reason', 'concise_observation',
    'concise_justification', 'concise_knowledge',
)
SCENARIO = '''NRFX invented factor proposal fixture. No instrument, market data or benchmark scores are available.
Propose at most four causal factors using past/current completed invented minute candles.
Any optional executable mapping must be a JSON object in variables.nrfx_formula, with exactly:
lookback (integer 5..240), feature_a, feature_b, feature_c (integer 0..5),
operator_ab, operator_c (integer 0..4), reverse (integer 0 or 1),
threshold (number 0.05..8), stop_usd (number 0.5..100),
reward_risk (number 0.2..10), cooldown (integer 1..1440).
Feature indices are scaled return, prior channel displacement, wick imbalance, close location,
second difference and volatility compression. Operator indices are add, subtract, multiply,
minimum and maximum. Apply operator_ab to A and B, then operator_c to that result and C.
Keep the required description and formulation as plain text. Return no code, commands, scores or future data.'''


class SourceError(RuntimeError):
    """The complete official package source tree was not verified."""


def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def _verified_source(checkout):
    root = checkout / 'rdagent'
    if not root.is_dir() or root.is_symlink():
        raise SourceError('Missing RD-Agent package source tree')
    paths = []
    for path in root.rglob('*'):
        if path.is_symlink() or path.name == '__pycache__':
            raise SourceError('RD-Agent checkout requires a pristine source tree')
        if not path.is_dir():
            paths.append(path)
            if len(paths) > SOURCE_FILE_COUNT or not path.is_file():
                raise SourceError('Unexpected RD-Agent package source file')
    source_hash = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.relative_to(checkout).as_posix()):
        if path.stat().st_size > 500_000:
            raise SourceError('Unexpected RD-Agent package source file size')
        relative = path.relative_to(checkout).as_posix().encode('utf-8')
        source_hash.update(relative + b'\0' + hashlib.sha256(path.read_bytes()).digest())
    if len(paths) != SOURCE_FILE_COUNT or source_hash.hexdigest() != SOURCE_TREE_SHA256:
        raise SourceError('RD-Agent package source differs from the pinned commit')
    return root


def _guard_process(mode):
    def audit(event, args):
        if event in ('subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn',
                     'os.fork', 'os.forkpty', 'os.startfile', 'os.startfile/2'):
            raise PermissionError('RD-Agent proposal cannot spawn another process')
        if event in ('socket.bind', 'socket.connect', 'socket.getaddrinfo', 'socket.gethostbyname',
                     'socket.gethostbyaddr', 'socket.getnameinfo', 'socket.sendto', 'socket.sendmsg'):
            if mode == 'ollama' and ((event == 'socket.connect' and args[1] == OLLAMA_ADDRESS)
                                     or (event == 'socket.getaddrinfo' and args[:2] == OLLAMA_ADDRESS)):
                return
            raise PermissionError('RD-Agent proposal cannot access this network endpoint')

    sys.addaudithook(audit)


def _unique_json(text, limit=MAX_REPLY_BYTES):
    def object_pairs(items):
        result = dict(items)
        if len(result) != len(items):
            raise ValueError('Duplicate structured provider response field')
        return result

    def reject_constant(_):
        raise ValueError('Non-finite structured provider response value')

    if not isinstance(text, str) or len(text.encode('utf-8')) > limit:
        raise ValueError('Invalid structured provider response size')
    return json.loads(text, object_pairs_hook=object_pairs, parse_constant=reject_constant)


def _text(value, limit=1000):
    return type(value) is str and 1 <= len(value) <= limit and bool(value.strip())


def validate_reply(reply, stage):
    if type(reply) is not dict:
        raise ValueError('RD-Agent expected a structured JSON object')
    if stage == 'hypothesis':
        if set(reply) != set(HYPOTHESIS_FIELDS) or not all(_text(value) for value in reply.values()):
            raise ValueError('Invalid RD-Agent hypothesis response')
    elif not 1 <= len(reply) <= MAX_TASKS or any(
            not _text(name, 80) or type(row) is not dict or set(row) != {'description', 'formulation', 'variables'}
            or not _text(row['description']) or not _text(row['formulation']) or type(row['variables']) is not dict
            for name, row in reply.items()):
        raise ValueError('Invalid RD-Agent factor task response')
    return reply


def _fixture_reply(seed, stage):
    rng = random.Random(seed)
    lookback = rng.choice((12, 16, 20, 24, 30))
    threshold = rng.choice((.35, .5, .65, .8))
    title = f'Combine scaled return and candle structure over {lookback} completed minutes'
    if stage == 'hypothesis':
        return {
            'hypothesis': title,
            'reason': 'A complementary candle feature can distinguish different price path shapes in an invented fixture.',
            'concise_reason': 'Complementary causal features.',
            'concise_observation': 'The fixture has invented price movement only.',
            'concise_justification': 'Compare a predefined arithmetic feature combination.',
            'concise_knowledge': 'Use completed candles and past observations only.',
        }
    return {'causal_candle_mix': {
        'description': title,
        'formulation': '(scaled_return + wick_imbalance) - prior_channel_displacement',
        'variables': {'nrfx_formula': {
            'lookback': lookback, 'feature_a': 0, 'feature_b': 2, 'feature_c': 1,
            'operator_ab': 0, 'operator_c': 1, 'reverse': 0, 'threshold': threshold,
            'stop_usd': 1.5, 'reward_risk': 1.5, 'cooldown': 10,
        }},
    }}


def _ollama_json(method, path, request=None, *, timeout=30, limit=MAX_REPLY_BYTES):
    conn = HTTPConnection(*OLLAMA_ADDRESS, timeout=timeout)
    try:
        conn.request(method, path, body=request, headers={'Content-Type': 'application/json'})
        response = conn.getresponse()
        if response.status != 200:
            raise RuntimeError('Local Ollama rejected the bounded request')
        payload = response.read(limit + 1)
        return _unique_json(payload.decode('utf-8'), limit)
    finally:
        conn.close()


def _tag(model):
    return model if ':' in model else f'{model}:latest'


def _ollama_digest(model):
    response = _ollama_json('GET', '/api/tags', timeout=5, limit=65_536)
    models = response.get('models') if isinstance(response, dict) else None
    if not isinstance(models, list):
        raise ValueError('Local Ollama did not return its model list')
    matches = [entry for entry in models if isinstance(entry, dict) and isinstance(entry.get('model'), str)
               and _tag(entry['model']) == _tag(model)]
    if len(matches) != 1:
        raise ValueError('Configured model is missing from the local Ollama inventory')
    entry = matches[0]
    model_digest = entry.get('digest')
    if (type(model_digest) is not str or not _HEX.fullmatch(model_digest)
            or type(entry.get('size')) is not int or entry['size'] <= 0
            or entry.get('remote_model') or entry.get('remote_host')):
        raise ValueError('Local Ollama model has no verified inventory digest')
    return model_digest


def _ollama_reply(model, seed, system_prompt, user_prompt):
    request = json.dumps({
        'model': model, 'stream': False, 'format': 'json',
        'messages': [{'role': 'system', 'content': system_prompt}, {'role': 'user', 'content': user_prompt}],
        'options': {'temperature': 0, 'seed': seed, 'num_predict': 1500},
    }).encode('utf-8')
    envelope = _ollama_json('POST', '/api/chat', request)
    if (not isinstance(envelope, dict) or envelope.get('done') is not True
            or not isinstance(envelope.get('model'), str) or _tag(envelope['model']) != _tag(model)):
        raise ValueError('Local Ollama response did not finish with the configured model')
    message = envelope.get('message')
    if not isinstance(message, dict) or message.get('role') != 'assistant' or message.get('tool_calls'):
        raise ValueError('Local Ollama must supply structured data without tool calls')
    return _unique_json(message.get('content'))


class ProposalProvider:
    def __init__(self, mode, seed, model):
        self.mode = mode
        self.seed = seed
        self.model = model
        self.attempts = 0
        self.calls = []

    def build_messages_and_create_chat_completion(self, user_prompt, system_prompt, *, json_mode, json_target_type):
        stage = ('hypothesis', 'experiment')[min(self.attempts, 1)]
        self.attempts += 1
        expected_type = dict[str, str] if stage == 'hypothesis' else dict[str, dict[str, str | dict]]
        if (self.attempts > 2 or len(self.calls) != self.attempts - 1 or not json_mode
                or json_target_type != expected_type or 'NRFX invented factor proposal fixture' not in system_prompt
                or not user_prompt.strip()):
            raise ValueError('Unexpected pinned RD-Agent proposal provider call')
        reply = validate_reply(
            _fixture_reply(self.seed, stage) if self.mode == 'fixture' else
            _ollama_reply(self.model, self.seed, system_prompt, user_prompt), stage,
        )
        self.calls.append({'stage': stage, 'prompt_sha256': digest([system_prompt, user_prompt]),
                           'reply_sha256': digest(reply)})
        return json.dumps(reply, ensure_ascii=True, allow_nan=False)


def _run(checkout, mode, seed, model, expected_model_digest=None):
    source = _verified_source(checkout)
    # The verified official package is a namespace package. Scope imports to
    # it without putting the rest of the checkout on the module search path.
    if 'rdagent' in sys.modules:
        raise SourceError('RD-Agent was imported before source verification')
    spec = importlib.machinery.ModuleSpec('rdagent', loader=None, is_package=True)
    spec.submodule_search_locations = [str(source)]
    sys.modules['rdagent'] = importlib.util.module_from_spec(spec)
    _guard_process(mode)

    from rdagent.log import rdagent_logger

    # The receipt is the only persisted evidence. Disable vendor template
    # pickles and process-tree logging in this isolated child.
    rdagent_logger.log_object = rdagent_logger._log = lambda *args, **kwargs: None

    from rdagent.components import proposal
    from rdagent.components.coder.factor_coder.factor import FactorTask
    from rdagent.core.proposal import ExperimentPlan, Hypothesis, Trace
    from rdagent.core.scenario import Scenario
    from rdagent.scenarios.qlib.experiment.factor_experiment import QlibFactorExperiment
    from rdagent.scenarios.qlib.proposal.factor_proposal import (
        QlibFactorHypothesis2Experiment, QlibFactorHypothesisGen,
    )

    class InventedFactorScenario(Scenario):
        background = SCENARIO
        rich_style_description = SCENARIO

        def get_scenario_all_desc(self, task=None, filtered_tag=None, simple_background=None):
            return self.background

        def get_runtime_environment(self):
            return 'Isolated proposal stages and an invented fixture'

    scenario = InventedFactorScenario()
    trace = Trace(scenario)
    provider = ProposalProvider(mode, seed, model)
    model_digest = _ollama_digest(model) if mode == 'ollama' else None
    if model_digest != expected_model_digest:
        raise RuntimeError('Local Ollama model inventory differs from the operator pin')
    with patch.object(proposal, 'APIBackend', return_value=provider):
        hypothesis = QlibFactorHypothesisGen(scenario).gen(trace, ExperimentPlan())
        experiment = QlibFactorHypothesis2Experiment().convert(hypothesis, trace)
    if model_digest is not None and _ollama_digest(model) != model_digest:
        raise RuntimeError('Local Ollama model inventory digest changed during the proposal')

    if (type(hypothesis) is not Hypothesis or type(experiment) is not QlibFactorExperiment
            or experiment.hypothesis is not hypothesis or experiment.result is not None
            or len(provider.calls) != 2 or any(type(task) is not FactorTask or task.factor_implementation
                                               for task in experiment.sub_tasks)):
        raise RuntimeError('RD-Agent did not produce the expected native objects')
    return {
        'hypothesis': {field: getattr(hypothesis, field) for field in HYPOTHESIS_FIELDS},
        'experiment_class': f'{type(experiment).__module__}.{type(experiment).__name__}',
        'tasks': [{'name': task.factor_name, 'description': task.factor_description,
                   'formulation': task.factor_formulation, 'variables': task.variables}
                  for task in experiment.sub_tasks],
        'provider_calls': provider.calls, 'model_digest': model_digest,
    }


def main():
    checkout, mode, seed, model, model_digest = sys.argv[1:]
    with open(os.devnull, 'w', encoding='utf-8') as sink, redirect_stdout(sink), redirect_stderr(sink):
        try:
            result = _run(Path(checkout), mode, int(seed), model, model_digest or None)
        except SourceError:
            return 2
        except ModuleNotFoundError:
            return 3
        except Exception:
            return 4
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
