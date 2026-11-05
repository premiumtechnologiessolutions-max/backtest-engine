"""Run a fixed policy through a pinned official FinRL StockTradingEnv."""
from __future__ import annotations

import hashlib
from importlib import metadata, util
import json
import math
import os
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd

PINNED_FINRL_COMMIT = '7e98df461cbc7772f16a545a2f13b521e5d0b8f4'
PINNED_FINRL_SOURCE_SHA256 = 'd2d7539cbcc0b386e698bfccffac4eb218e2100efb40a7eb2662f24c891dc520'
_SOURCE_FILE = Path('finrl/meta/env_stock_trading/env_stocktrading.py')
_SOURCE_SIZE = 23_862
_DEPENDENCIES = ('gymnasium', 'matplotlib', 'stable_baselines3', 'torch')
_ASSETS = ('SIM_A', 'SIM_B')
_INITIAL_CASH = 10_000
_COST_RATES = (0.001, 0.0015)
_REWARD_SCALING = 0.01


class FinRLUnavailable(RuntimeError):
    """The pinned FinRL source or its optional dependencies are unavailable."""


def _verified_source() -> bytes:
    location = os.environ.get('NRFX_FINRL_SOURCE')
    if not location:
        raise FinRLUnavailable('Set NRFX_FINRL_SOURCE to the pinned FinRL source checkout')
    path = Path(location) / _SOURCE_FILE
    try:
        if not path.is_file():
            raise FinRLUnavailable('The FinRL checkout does not contain StockTradingEnv')
        with path.open('rb') as stream:
            source = stream.read(_SOURCE_SIZE + 1)
    except OSError as exc:
        raise FinRLUnavailable('The FinRL source cannot be read') from exc
    if len(source) != _SOURCE_SIZE or hashlib.sha256(source).hexdigest() != PINNED_FINRL_SOURCE_SHA256:
        raise FinRLUnavailable('FinRL StockTradingEnv source differs from the pinned revision')
    return source


def finrl_status() -> dict:
    """Report static availability. Actual execution requires a saved receipt."""
    try:
        _verified_source()
        source_verified = True
    except FinRLUnavailable:
        source_verified = False
    missing = [name for name in _DEPENDENCIES if util.find_spec(name) is None]
    return {
        'installed': source_verified and not missing,
        'source_verified': source_verified,
        'required_version': PINNED_FINRL_COMMIT,
        'source_sha256': PINNED_FINRL_SOURCE_SHA256,
        'missing_dependencies': missing,
        'mode': 'synthetic_fixed_policy',
        'execution_verified': False,
    }


def _load_environment():
    source = _verified_source()
    # Import exactly the audited environment bytes. The FinRL package root
    # initializes unrelated data-provider, training and live-trading modules.
    module = ModuleType('_nrfx_verified_finrl_stocktrading')
    try:
        exec(compile(source, str(_SOURCE_FILE), 'exec'), module.__dict__)
    except ImportError as exc:
        raise FinRLUnavailable('Install compatible Gymnasium, Matplotlib, Stable-Baselines3 and Torch') from exc
    return module.StockTradingEnv


def _validate(bars, seed):
    if type(bars) is not int or not 40 <= bars <= 2000:
        raise ValueError('Synthetic FinRL fixture requires 40..2000 bars')
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError('Synthetic fixture seed must be an unsigned 32-bit integer')


def _fixture(bars, seed):
    rng = np.random.default_rng(seed)
    noise = rng.uniform(-0.4, 0.4, size=(bars, len(_ASSETS)))
    oscillation = np.sin(np.arange(bars)[:, None] / np.array([9., 13.])) * np.array([2., 3.])
    prices = np.round(np.array([42., 73.]) + oscillation + noise, 4)
    dates = pd.date_range('2020-01-06', periods=bars, freq='D').strftime('%Y-%m-%d')
    return pd.DataFrame({
        'date': np.repeat(dates, len(_ASSETS)),
        'tic': np.tile(_ASSETS, bars),
        'close': prices.ravel(),
    }, index=np.repeat(np.arange(bars), len(_ASSETS)))


def _actions(step, bars):
    if step == bars - 2 or step % 4 == 2:
        return np.array([-1., -1.])
    if step < bars - 2 and step % 4 == 0:
        return np.array([0.5, 0.25])
    return np.zeros(len(_ASSETS))


def _reconcile(env, prices, bars):
    assets = np.asarray(env.asset_memory, dtype=float)
    actions = np.asarray(env.actions_memory, dtype=np.int64)
    if assets.shape != (bars,) or actions.shape != (bars - 1, len(_ASSETS)):
        raise RuntimeError('FinRL did not publish a complete native trajectory')
    position = actions.cumsum(axis=0)
    closes = prices[:-1]
    fees = (np.abs(actions) * closes * np.asarray(_COST_RATES)).sum(axis=1)
    cash = _INITIAL_CASH - ((actions * closes).sum(axis=1) + fees).cumsum()
    valued = np.r_[_INITIAL_CASH, cash + (position * prices[1:]).sum(axis=1)]
    count = int(np.count_nonzero(actions))
    if (not np.isfinite(assets).all() or (position < 0).any() or position[-1].any()
            or count < 4 or count != env.trades
            or not np.allclose(assets, valued, rtol=1e-12, atol=1e-8)
            or not math.isclose(env.cost, float(fees.sum()), rel_tol=1e-12, abs_tol=1e-8)):
        raise RuntimeError('FinRL fills, fees or account values failed reconciliation')
    return assets, actions, count


def run_finrl_synthetic(bars=240, seed=0) -> dict:
    """Execute FinRL's Gymnasium environment with invented stock prices."""
    _validate(bars, seed)
    environment = _load_environment()
    fixture = _fixture(bars, seed)
    asset_count = len(_ASSETS)
    env = environment(df=fixture, stock_dim=asset_count, hmax=8,
                      initial_amount=_INITIAL_CASH, num_stock_shares=[0] * asset_count,
                      buy_cost_pct=list(_COST_RATES), sell_cost_pct=list(_COST_RATES),
                      reward_scaling=_REWARD_SCALING, state_space=1 + 2 * asset_count,
                      action_space=asset_count, tech_indicator_list=[],
                      make_plots=False, print_verbosity=2)
    try:
        env.reset(seed=seed)
        for step in range(bars):
            _, _, terminated, truncated, _ = env.step(_actions(step, bars))
            if truncated or bool(terminated) != (step == bars - 1):
                raise RuntimeError('FinRL did not complete the bounded Gymnasium episode')
        prices = fixture['close'].to_numpy().reshape(bars, asset_count)
        assets, actions, fills_count = _reconcile(env, prices, bars)
        result = {
            'schema': 'NRFX_FINRL_SYNTHETIC_RUNTIME_V1',
            'engine': 'finrl', 'engine_version': PINNED_FINRL_COMMIT,
            'environment': 'StockTradingEnv', 'source_sha256': PINNED_FINRL_SOURCE_SHA256,
            'dependencies': {name: metadata.version(name) for name in _DEPENDENCIES},
            'runtime_executed': True, 'fixture': 'INVENTED_TWO_STOCK_DAILY_BARS',
            'fixture_sha256': hashlib.sha256(fixture.to_csv(index=False).encode()).hexdigest(),
            'bars': bars, 'seed': seed, 'policy': 'fixed_buy_hold_sell_flat_cycle',
            'rl_training_executed': False, 'observation_steps': bars,
            'native_assets': list(_ASSETS), 'native_account_value': assets.tolist(),
            'native_share_changes': actions.tolist(), 'fills_count': fills_count,
            'initial_cash': float(assets[0]), 'final_cash': float(assets[-1]),
            'fee_cost': float(env.cost), 'final_holdings': [0] * asset_count,
            'market_data_accessed': False, 'network_requested': False,
            'broker_orders_sent': False, 'canonical_execution_parity_verified': False,
            'profitability_claimed': False,
        }
        result['deterministic_sha256'] = hashlib.sha256(json.dumps(
            result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        return result
    finally:
        env.close()
