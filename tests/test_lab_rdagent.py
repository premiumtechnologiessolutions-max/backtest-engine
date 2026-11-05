import json
import os
import subprocess
import sys

import pytest

from norisk_quant import _rdagent_probe as probe
from norisk_quant import lab_rdagent as rdagent
from norisk_quant.math_discovery import Formula


def test_rdagent_status_requires_explicit_isolated_configuration(monkeypatch, tmp_path):
    monkeypatch.delenv(rdagent.RDAGENT_PYTHON_ENV, raising=False)
    monkeypatch.delenv(rdagent.RDAGENT_CHECKOUT_ENV, raising=False)
    assert not rdagent.rdagent_status()['configured']
    with pytest.raises(rdagent.RDAgentUnavailable):
        rdagent.run_rdagent_probe()
    with pytest.raises(ValueError):
        rdagent.run_rdagent_probe(seed=True)

    (tmp_path / 'rdagent').mkdir()
    monkeypatch.setenv(rdagent.RDAGENT_PYTHON_ENV, sys.executable)
    monkeypatch.setenv(rdagent.RDAGENT_CHECKOUT_ENV, str(tmp_path))
    monkeypatch.setenv(rdagent.RDAGENT_MODEL_DIGEST_ENV, 'a' * 64)
    monkeypatch.setenv(rdagent.RDAGENT_MODEL_ENV, 'model:latest-cloud')
    assert rdagent.rdagent_status()['configured']
    assert not rdagent.rdagent_status()['ollama_configured']
    monkeypatch.setenv(rdagent.RDAGENT_MODEL_ENV, 'model:latest')
    assert rdagent.rdagent_status('ollama')['model_digest'] == 'a' * 64
    assert not rdagent.rdagent_status('ollama')['runtime_verified']
    with pytest.raises(rdagent.RDAgentUnavailable, match='source failed verification'):
        rdagent.run_rdagent_probe()


def test_native_task_mapping_only_admits_exact_typed_formula():
    formula = probe._fixture_reply(0, 'experiment')['causal_candle_mix']['variables']['nrfx_formula']
    tasks = [
        {'name': 'valid', 'variables': {'nrfx_formula': formula}},
        {'name': 'duplicate', 'variables': {'nrfx_formula': {**formula, 'stop_usd': 1.5}}},
        {'name': 'extra_code', 'variables': {'nrfx_formula': {**formula, 'code': 'arbitrary text'}}},
        {'name': 'untagged', 'variables': formula},
    ]
    envelope, mappings = rdagent._map_tasks(tasks)
    assert envelope['proposals'] == [formula]
    assert [mapping['status'] for mapping in mappings] == [
        'MAPPED_TYPED_FORMULA', 'DUPLICATE_TYPED_FORMULA', 'INVALID_TYPED_FORMULA', 'NO_TYPED_FORMULA',
    ]
    assert mappings[0]['formula_identity'] == Formula(**formula).identity()
    assert rdagent._map_tasks(tasks[-2:])[0] is None


def test_native_receipt_binds_experiment_and_rejects_provider_tampering():
    hypothesis = probe._fixture_reply(0, 'hypothesis')
    experiment = probe._fixture_reply(0, 'experiment')
    native = {
        'hypothesis': hypothesis, 'experiment_class': rdagent._EXPERIMENT_CLASS, 'model_digest': None,
        'tasks': [{'name': name, **task} for name, task in experiment.items()],
        'provider_calls': [{'stage': stage, 'prompt_sha256': '1' * 64, 'reply_sha256': probe.digest(value)}
                           for stage, value in [('hypothesis', hypothesis), ('experiment', experiment)]],
    }
    assert rdagent._read_native_result(json.dumps(native), None) == native
    native['tasks'][0]['variables']['nrfx_formula']['lookback'] = 55
    with pytest.raises(rdagent.RDAgentRuntimeError, match='receipt'):
        rdagent._read_native_result(json.dumps(native), None)
    with pytest.raises(ValueError, match='Duplicate'):
        probe._unique_json('{"lookback": 10, "lookback": 55}')


def test_ollama_provider_uses_fixed_loopback_and_pinned_inventory(monkeypatch):
    calls = []
    model_digest = 'f' * 64
    replies = iter([
        {'models': [{'model': 'test:latest', 'digest': model_digest, 'size': 42}]},
        {'model': 'test:latest', 'done': True, 'message': {'role': 'assistant', 'content': '{"example":1}'}},
        {'models': [{'model': 'test:latest', 'digest': model_digest, 'size': 42, 'remote_host': 'outside'}]},
    ])

    class Connection:
        def __init__(self, host, port, *, timeout):
            assert (host, port) == ('127.0.0.1', 11434)

        def request(self, method, path, body, headers):
            calls.append((method, path, json.loads(body) if body else None))

        def getresponse(self):
            return self

        status = 200

        def read(self, length):
            return json.dumps(next(replies)).encode()[:length]

        def close(self):
            pass

    monkeypatch.setattr(probe, 'HTTPConnection', Connection)
    assert probe._ollama_digest('test') == model_digest
    assert probe._ollama_reply('test', 5, 'synthetic scenario', 'invented prompt') == {'example': 1}
    assert [call[:2] for call in calls] == [('GET', '/api/tags'), ('POST', '/api/chat')]
    assert calls[1][2]['options']['seed'] == 5
    assert calls[1][2]['format'] == 'json'
    with pytest.raises(ValueError, match='inventory digest'):
        probe._ollama_digest('test')


def test_official_rdagent_fixture_through_normal_lab_cli(tmp_path):
    if os.environ.get('NRFX_REQUIRE_RDAGENT') != '1' and not rdagent.rdagent_status()['available']:
        pytest.skip('optional pinned native RD-Agent proposal runtime is not configured')
    cli = [sys.executable, '-m', 'norisk_quant.lab_cli', '--database', str(tmp_path / 'jobs.sqlite')]
    done = subprocess.run([*cli, 'rdagent-demo', '--seed', '4'], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, (done.stdout, done.stderr)
    job = json.loads(done.stdout)
    assert job['state'] == 'SUCCEEDED'
    result = job['result']
    assert result['source_tree_verified'] and result['runtime_executed']
    assert result['vendor_commit'] == rdagent.PINNED_RDAGENT_COMMIT
    assert result['native']['experiment_class'] == rdagent._EXPERIMENT_CLASS
    assert result['native_task_count'] == 1
    assert not result['model_inference_executed']
    assert not result['network_requested'] and not result['market_data_accessed']
    assert not result['generated_code_executed'] and not result['qlib_backtest_executed']
    assert result['canonical_evaluation']['status'] == 'EVALUATED_SYNTHETIC_ONLY'
    assert len(result['candidates']) == 1 and result['candidates'][0]['parity_passed']
    assert result['candidates'][0]['id'] == result['formula_mappings'][0]['formula_identity']
    assert result['proposal_binding_sha256'] == probe.digest({
        'native': result['native'], 'formula_envelope': result['formula_envelope'],
    })
    assert result['deterministic_sha256'] == rdagent.run_rdagent_probe(seed=4)['deterministic_sha256']
    status = subprocess.run([*cli, 'status'], capture_output=True, text=True, check=True, timeout=30)
    capability = json.loads(status.stdout)['vendors']['rdagent_factor_synthetic']
    assert capability['fixture_execution_verified'] and not capability['model_inference_verified']
