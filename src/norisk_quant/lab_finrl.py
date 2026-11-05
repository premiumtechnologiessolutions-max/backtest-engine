"""Run fixed and trained policies through a pinned FinRL StockTradingEnv."""
from __future__ import annotations

import hashlib
from importlib import metadata, util
import json
import math
import os
from pathlib import Path
import random
from threading import Lock
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
_TRADE_SHARES = 8
_TRAINING_TIMESTEPS = 512
_TRAINING_BARS_CAP = 128
_PPO_VERSION = '2.6.0'
_PPO_LOCK = Lock()


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
    try:
        training_version = metadata.version('stable_baselines3')
    except metadata.PackageNotFoundError:
        training_version = None
    return {
        'installed': source_verified and not missing,
        'source_verified': source_verified,
        'required_version': PINNED_FINRL_COMMIT,
        'source_sha256': PINNED_FINRL_SOURCE_SHA256,
        'missing_dependencies': missing,
        'mode': 'synthetic_fixed_policy',
        'training_mode': 'synthetic_ppo',
        'training_installed': source_verified and not missing and training_version == _PPO_VERSION,
        'required_training_version': _PPO_VERSION,
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


def _fixture(bars, seed, *, varied_phase=False):
    rng = np.random.default_rng(seed)
    noise = rng.uniform(-0.4, 0.4, size=(bars, len(_ASSETS)))
    phase = rng.uniform(0, 2 * np.pi, size=len(_ASSETS)) if varied_phase else 0
    oscillation = np.sin(np.arange(bars)[:, None] / np.array([9., 13.]) + phase) * np.array([2., 3.])
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


def _reconcile(env, prices, bars, *, minimum_fills):
    assets = np.asarray(env.asset_memory, dtype=float)
    native_actions = np.asarray(env.actions_memory)
    actions = native_actions.astype(np.int64)
    if assets.shape != (bars,) or actions.shape != (bars - 1, len(_ASSETS)):
        raise RuntimeError('FinRL did not publish a complete native trajectory')
    if not np.array_equal(native_actions, actions):
        raise RuntimeError('FinRL recorded nonintegral share changes')
    position = actions.cumsum(axis=0)
    closes = prices[:-1]
    fees = (np.abs(actions) * closes * np.asarray(_COST_RATES)).sum(axis=1)
    cash = _INITIAL_CASH - ((actions * closes).sum(axis=1) + fees).cumsum()
    valued = np.r_[_INITIAL_CASH, cash + (position * prices[1:]).sum(axis=1)]
    count = int(np.count_nonzero(actions))
    native_holdings = np.asarray(env.state[1 + len(_ASSETS):])
    if (not np.isfinite(assets).all() or (position < 0).any() or position[-1].any()
            or native_holdings.any() or (cash < -1e-8).any()
            or count < minimum_fills or count > env.trades
            or not np.allclose(assets, valued, rtol=1e-12, atol=1e-8)
            or not math.isclose(env.cost, float(fees.sum()), rel_tol=1e-12, abs_tol=1e-8)
            or not math.isclose(env.state[0], cash[-1], rel_tol=1e-12, abs_tol=1e-8)):
        raise RuntimeError('FinRL fills, fees or account values failed reconciliation')
    return assets, actions, count


def _new_environment(environment, fixture):
    asset_count = len(_ASSETS)
    return environment(df=fixture, stock_dim=asset_count, hmax=_TRADE_SHARES,
                       initial_amount=_INITIAL_CASH, num_stock_shares=[0] * asset_count,
                       buy_cost_pct=list(_COST_RATES), sell_cost_pct=list(_COST_RATES),
                       reward_scaling=_REWARD_SCALING, state_space=1 + 2 * asset_count,
                       action_space=asset_count, tech_indicator_list=[],
                       make_plots=False, print_verbosity=_TRAINING_TIMESTEPS + 1)


def _receipt(env, fixture, bars, seed, *, schema, policy, minimum_fills, **details):
    asset_count = len(_ASSETS)
    prices = fixture['close'].to_numpy().reshape(bars, asset_count)
    assets, actions, fills_count = _reconcile(env, prices, bars, minimum_fills=minimum_fills)
    result = {
        'schema': schema,
        'engine': 'finrl', 'engine_version': PINNED_FINRL_COMMIT,
        'environment': 'StockTradingEnv', 'source_sha256': PINNED_FINRL_SOURCE_SHA256,
        'dependencies': {name: metadata.version(name) for name in _DEPENDENCIES},
        'runtime_executed': True, 'fixture': 'INVENTED_TWO_STOCK_DAILY_BARS',
        'fixture_sha256': _fixture_hash(fixture),
        'bars': bars, 'seed': seed, 'policy': policy, 'observation_steps': bars,
        'native_assets': list(_ASSETS), 'native_account_value': assets.tolist(),
        'native_share_changes': actions.tolist(), 'fills_count': fills_count,
        'initial_cash': float(assets[0]), 'final_cash': float(assets[-1]),
        'fee_cost': float(env.cost), 'final_holdings': [0] * asset_count,
        'market_data_accessed': False, 'network_requested': False,
        'broker_orders_sent': False, 'canonical_execution_parity_verified': False,
        'profitability_claimed': False,
        **details,
    }
    result['deterministic_sha256'] = hashlib.sha256(json.dumps(
        result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return result


def _fixture_hash(fixture):
    return hashlib.sha256(fixture.to_csv(index=False, lineterminator='\n').encode()).hexdigest()


def run_finrl_synthetic(bars=240, seed=0) -> dict:
    """Execute FinRL's Gymnasium environment with invented stock prices."""
    _validate(bars, seed)
    environment = _load_environment()
    fixture = _fixture(bars, seed)
    env = _new_environment(environment, fixture)
    try:
        env.reset(seed=seed)
        for step in range(bars):
            _, _, terminated, truncated, _ = env.step(_actions(step, bars))
            if truncated or bool(terminated) != (step == bars - 1):
                raise RuntimeError('FinRL did not complete the bounded Gymnasium episode')
        return _receipt(env, fixture, bars, seed, schema='NRFX_FINRL_SYNTHETIC_RUNTIME_V1',
                        policy='fixed_buy_hold_sell_flat_cycle', minimum_fills=4,
                        rl_training_executed=False)
    finally:
        env.close()


def _ppo_environment(gym, native, bars):
    class BoundedTrading(gym.Wrapper):
        """Normalize observations and map three per-asset actions to native trades."""

        def __init__(self, env):
            super().__init__(env)
            self.action_space = gym.spaces.MultiDiscrete([3] * len(_ASSETS))
            self.scale = np.array([_INITIAL_CASH, 100., 100., 250., 250.], dtype=np.float32)

        def reset(self, *, seed=None, options=None):
            observation, info = self.env.reset(seed=seed, options=options)
            return np.asarray(observation, dtype=np.float32) / self.scale, info

        def step(self, action):
            step = self.env.day
            if step == bars - 2:
                # FinRL caps each sale at hmax. Allow the full inventory to
                # close at this last tradable observation with native fees.
                previous_hmax = self.env.hmax
                self.env.hmax = int(max(previous_hmax, *self.env.state[1 + len(_ASSETS):]))
                try:
                    transition = self.env.step(-np.ones(len(_ASSETS)))
                finally:
                    self.env.hmax = previous_hmax
            else:
                transition = self.env.step(np.asarray(action, dtype=np.float32) - 1.)
            observation, reward, terminated, truncated, info = transition
            # FinRL's final, non-trading call repeats its previous reward.
            return (np.asarray(observation, dtype=np.float32) / self.scale,
                    0. if terminated else reward, terminated, truncated, info)

    return BoundedTrading(native)


def _policy_hash(model):
    digest = hashlib.sha256()
    for name, tensor in model.policy.state_dict().items():
        array = tensor.detach().cpu().numpy()
        if not np.isfinite(array).all():
            raise RuntimeError('PPO produced nonfinite policy parameters')
        digest.update(repr((name, array.shape, array.dtype.str)).encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


def run_finrl_training_synthetic(bars=240, seed=0) -> dict:
    """Train bounded CPU PPO and evaluate its frozen policy on an invented fixture."""
    _validate(bars, seed)
    environment = _load_environment()
    import gymnasium as gym
    import torch
    from stable_baselines3 import PPO

    if metadata.version('stable_baselines3') != _PPO_VERSION:
        raise FinRLUnavailable(f'Synthetic training requires stable-baselines3=={_PPO_VERSION}')

    seeds = [int(child.generate_state(1)[0]) for child in np.random.SeedSequence(seed).spawn(4)]
    training_seed, evaluation_seed, model_seed, action_seed = seeds
    training_bars = min(bars, _TRAINING_BARS_CAP)
    training_fixture = _fixture(training_bars, training_seed, varied_phase=True)
    evaluation_fixture = _fixture(bars, evaluation_seed, varied_phase=True)
    training_env = _ppo_environment(gym, _new_environment(environment, training_fixture), training_bars)
    native_eval = _new_environment(environment, evaluation_fixture)
    evaluation_env = _ppo_environment(gym, native_eval, bars)
    try:
        # SB3 configures global random generators. Keep training jobs from
        # interleaving them and restore caller RNG/thread state afterward.
        with _PPO_LOCK, torch.random.fork_rng(devices=[]):
            python_rng, numpy_rng = random.getstate(), np.random.get_state()
            thread_count = torch.get_num_threads()
            try:
                torch.set_num_threads(1)
                model = PPO('MlpPolicy', training_env, device='cpu', seed=model_seed,
                            n_steps=64, batch_size=32, n_epochs=4, verbose=0,
                            policy_kwargs={'net_arch': {'pi': [16, 16], 'vf': [16, 16]}})
                initial_hash = _policy_hash(model)
                model.learn(total_timesteps=_TRAINING_TIMESTEPS)
                trained_hash = _policy_hash(model)
                if model.num_timesteps != _TRAINING_TIMESTEPS or trained_hash == initial_hash:
                    raise RuntimeError('PPO did not finish bounded training and update its parameters')

                model.policy.set_training_mode(False)
                torch.manual_seed(action_seed)
                observation, _ = evaluation_env.reset(seed=evaluation_seed)
                for step in range(bars):
                    action = np.ones(len(_ASSETS), dtype=int)
                    if step < bars - 2:
                        # Sample the trained distribution reproducibly; no
                        # policy or optimizer update is allowed in evaluation.
                        action, _ = model.predict(observation, deterministic=False)
                    observation, _, terminated, truncated, _ = evaluation_env.step(action)
                    if truncated or bool(terminated) != (step == bars - 1):
                        raise RuntimeError('FinRL did not complete frozen-policy evaluation')
                if _policy_hash(model) != trained_hash:
                    raise RuntimeError('PPO policy changed during evaluation')
            finally:
                torch.set_num_threads(thread_count)
                random.setstate(python_rng)
                np.random.set_state(numpy_rng)

        return _receipt(
            native_eval, evaluation_fixture, bars, seed, schema='NRFX_FINRL_SYNTHETIC_TRAINING_V1',
            policy='frozen_ppo_seeded_sampling', minimum_fills=0, rl_training_executed=True,
            training_algorithm='Stable-Baselines3 PPO', training_device='cpu',
            training_timesteps=model.num_timesteps, training_bars=training_bars,
            training_fixture_seed=training_seed, training_fixture_sha256=_fixture_hash(training_fixture),
            evaluation_fixture_seed=evaluation_seed, evaluation_fixture_sha256=_fixture_hash(evaluation_fixture),
            initial_policy_sha256=initial_hash, trained_policy_sha256=trained_hash,
            evaluation_action_seed=action_seed, model_seed=model_seed,
            evaluation_policy_frozen=True, evaluation_market_out_of_sample=False,
            terminal_liquidation_enforced=True, evaluation_policy_steps=bars - 2,
            native_trade_counter=int(native_eval.trades),  # includes zero-size buys
        )
    finally:
        evaluation_env.close()
        training_env.close()
