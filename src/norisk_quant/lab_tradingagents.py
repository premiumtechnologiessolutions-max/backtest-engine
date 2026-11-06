"""Run the pinned TradingAgents graph in its own Python environment."""
from __future__ import annotations

from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from ._tradingagents_worker import PIN, SYMBOL

_ENV_PYTHON = 'NRFX_TRADINGAGENTS_PYTHON'
_ENV_MODEL = 'NRFX_TRADINGAGENTS_OLLAMA_MODEL'
_MAX_OUTPUT = 128 * 1024


class TradingAgentsUnavailable(RuntimeError):
    """Pinned TradingAgents graph runtime or local model is unavailable."""


def _local_model():
    name = os.environ.get(_ENV_MODEL, '')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}(?::[A-Za-z0-9][A-Za-z0-9_.-]{0,31})?', name):
        raise TradingAgentsUnavailable('Configure a named local Ollama model')
    if 'cloud' in name.lower():
        raise TradingAgentsUnavailable('Cloud Ollama model tags are disabled')
    return name if ':' in name else name + ':latest'


def _invoke(action, request, *, timeout):
    setting = os.environ.get(_ENV_PYTHON, '')
    executable = Path(setting).expanduser()
    if not setting or not executable.is_absolute() or not executable.is_file():
        raise TradingAgentsUnavailable('Configure the separate pinned TradingAgents Python environment')
    env = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR') if key in os.environ}
    env.update(PYTHON_DOTENV_DISABLED='1', LANGSMITH_TRACING='false', LANGCHAIN_TRACING_V2='false',
               OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
    worker = Path(__file__).resolve().with_name('_tradingagents_worker.py')
    try:
        with tempfile.TemporaryDirectory(prefix='nrfx-tradingagents-') as cwd:
            process = subprocess.run([str(executable), '-I', '-B', str(worker), action],
                input=json.dumps(request, allow_nan=False), capture_output=True, text=True, encoding='utf-8',
                cwd=cwd, env=env, check=True, timeout=timeout)
        if not 0 < len(process.stdout) <= _MAX_OUTPUT:
            raise ValueError('Invalid bounded TradingAgents output')
        return json.loads(process.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # Never copy model logs, private paths or arbitrary provider text into job errors.
        raise TradingAgentsUnavailable('Pinned TradingAgents worker could not complete') from exc


def tradingagents_status(mode='fixture'):
    if mode not in ('fixture', 'ollama'):
        raise ValueError('Unknown TradingAgents provider mode')
    status = {'upstream_commit': PIN, 'installed': False, 'mode': mode,
              'configured': bool(os.environ.get(_ENV_PYTHON)),
              'ollama_configured': bool(os.environ.get(_ENV_MODEL))}
    if status['configured']:
        try:
            model = _local_model() if mode == 'ollama' else None
            identity = _invoke('probe', {'mode': mode, 'model': model}, timeout=8)
        except TradingAgentsUnavailable:
            return status
        status.update(identity, installed=True)
    return status


def _fixture_sessions(frame):
    """Aggregate the lab's invented minute bars into 24 fictional sessions."""
    rows = []
    count = 24
    start = date(2024, 2, 1)
    for index in range(count):
        group = frame.iloc[index * len(frame) // count:(index + 1) * len(frame) // count]
        rows.append({'date': (start + timedelta(days=index)).isoformat(),
                     'open': round(float(group.o.iloc[0]), 6), 'high': round(float(group.h.max()), 6),
                     'low': round(float(group.l.min()), 6), 'close': round(float(group.c.iloc[-1]), 6),
                     'volume': len(group) * 100})
    return rows


def run_tradingagents_graph(*, bars=360, seed=0, mode='fixture', progress=lambda stage: None):
    """Execute official graph nodes with fixture replies or local Ollama inference."""
    from .lab_coordinator import _bounded, _frame_digest, synthetic_fixture

    bars = _bounded(bars, 'bars', 240, 1440)
    seed = _bounded(seed, 'seed', 0, 2**32 - 1)
    if mode not in ('fixture', 'ollama'):
        raise ValueError('Unknown TradingAgents provider mode')
    model = _local_model() if mode == 'ollama' else None
    progress('tradingagents_fixture')
    frame = synthetic_fixture(bars, seed)
    fixture_id = _frame_digest(frame)
    progress('tradingagents_official_graph')
    result = _invoke('run', {'mode': mode, 'model': model, 'fixture_sha256': fixture_id,
                             'sessions': _fixture_sessions(frame)},
                     timeout=210 if mode == 'ollama' else 60)
    if (result.get('fixture_sha256') != fixture_id or result.get('mode') != mode
            or result.get('official_graph_executed') is not True
            or result.get('model_inference_executed') is not (mode == 'ollama')):
        raise TradingAgentsUnavailable('TradingAgents result did not match the requested graph')
    return {**result, 'schema': 'NRFX_TRADINGAGENTS_SYNTHETIC_GRAPH_V1', 'engine': 'TradingAgents',
            'symbol': SYMBOL, 'bars': bars, 'seed': seed, 'runtime_executed': True,
            'provenance': 'SYNTHETIC_NOT_MARKET', 'market_data_accessed': False,
            'live_trading_enabled': False, 'independent_oos_proven': False}
