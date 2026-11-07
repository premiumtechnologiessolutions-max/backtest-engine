"""Causal arithmetic hypothesis grammar for exploratory Gold M1 research.

Not an AI language model or a profitable strategy: grammar permits the
research controller to discover testable arithmetic expressions WITHOUT eval,
network calls, mutable globals, retrospective fill assumptions, or future bars.
Every signal is confirmed at M1 close and can fill only at the next observed
open through the existing independent reference/fast execution engines.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import math
import numpy as np
import pandas as pd
from .model import Signal
from .strategy import aggregate_bars

FEATURES = (
    'scaled_return', 'prior_channel_displacement', 'wick_imbalance',
    'close_location', 'second_difference', 'volatility_compression',
)
OPERATORS = ('add', 'subtract', 'multiply', 'minimum', 'maximum')

@dataclass(frozen=True)
class Formula:
    lookback: int = 20
    feature_a: int = 0
    feature_b: int = 2
    feature_c: int = 1
    operator_ab: int = 0
    operator_c: int = 0
    reverse: int = 0
    threshold: float = 1.0
    stop_usd: float = 8.0
    reward_risk: float = 1.5
    cooldown: int = 10

    def __post_init__(self):
        for name, minimum, maximum in (
            ('lookback', 5, 240), ('feature_a', 0, len(FEATURES)-1),
            ('feature_b', 0, len(FEATURES)-1), ('feature_c', 0, len(FEATURES)-1),
            ('operator_ab', 0, len(OPERATORS)-1),
            ('operator_c', 0, len(OPERATORS)-1), ('reverse', 0, 1),
            ('cooldown', 1, 1440),
        ):
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f'{name} must be integer in [{minimum},{maximum}]')
        for name, lower, upper in (
            ('threshold', 0.05, 8.0), ('stop_usd', 0.5, 100.0),
            ('reward_risk', 0.2, 10.0),
        ):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not lower <= value <= upper:
                raise ValueError(f'{name} must be finite in [{lower},{upper}]')

    def identity(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True, separators=(',', ':')).encode()
        return hashlib.sha256(blob).hexdigest()

    def expression(self) -> str:
        a, b, c = (FEATURES[getattr(self, f'feature_{x}')]
                   for x in 'abc')
        return f"{'-' if self.reverse else ''}(({a} {OPERATORS[self.operator_ab]} {b}) {OPERATORS[self.operator_c]} {c})"


def _operator(a: np.ndarray, b: np.ndarray, which: int) -> np.ndarray:
    if which == 0: return a + b
    if which == 1: return a - b
    if which == 2: return a * b
    if which == 3: return np.minimum(a, b)
    return np.maximum(a, b)


def formula_scores(minutes: pd.DataFrame, formula: Formula) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Score completed observed M1 only; exact N+1 minute lookback is required."""
    bars = aggregate_bars(minutes, 'M1')
    if len(bars) <= formula.lookback:
        return bars, np.empty(0), np.empty(0, dtype=bool)
    raw = bars[['o', 'h', 'l', 'c']].to_numpy(dtype=np.float64)
    o,h,l,c = (raw[:,i] for i in range(4))
    if (not np.isfinite(raw).all() or (raw <= 0).any()
            or (h < np.maximum(o,c)).any() or (l > np.minimum(o,c)).any()
            or (h < l).any()):
        raise ValueError('Research formula requires coherent positive finite M1 OHLC')
    n = len(bars); k=formula.lookback
    pri_hi = bars['h'].rolling(k).max().shift(1).to_numpy()
    pri_lo = bars['l'].rolling(k).min().shift(1).to_numpy()
    pri_mean = bars['c'].rolling(k).mean().shift(1).to_numpy()
    # Volatility unit depends ONLY on previous fully observed candles.
    unit = (bars['h']-bars['l']).rolling(k).mean().shift(1).to_numpy()
    unit = np.maximum(unit, 0.01)
    lag_close = bars['c'].shift(k).to_numpy()
    prev1 = bars['c'].shift(1).to_numpy()
    prev2 = bars['c'].shift(2).to_numpy()
    span = np.maximum(h-l, 0.01)
    with np.errstate(invalid='ignore', divide='ignore', over='ignore'):
        features = np.column_stack((
            np.tanh((c-lag_close)/unit),
            np.tanh((c-pri_mean)/unit),
            (2*np.minimum(o,c)-2*l - (2*h-2*np.maximum(o,c)))/2/span,
            (2*c-h-l)/span,
            np.tanh((c-2*prev1+prev2)/unit),
            np.tanh(((h-l)/unit)-1),
        ))
    # Never treat a missing minute as continuous history. Even if a rolling
    # statistic exists, this historical feature window cannot be certified.
    valid = np.zeros(n, dtype=bool)
    valid[k:] = (bars.index[k:] - bars.index[:-k] == pd.Timedelta(minutes=k))
    valid &= np.isfinite(features).all(axis=1)
    score = _operator(_operator(features[:,formula.feature_a],
                                features[:,formula.feature_b],formula.operator_ab),
                      features[:,formula.feature_c],formula.operator_c)
    if formula.reverse: score = -score
    valid &= np.isfinite(score)
    return bars, score, valid


def arithmetic_signals(minutes: pd.DataFrame, formula: Formula | None = None,
                       **kwargs) -> list[Signal]:
    if formula is not None and kwargs:
        raise ValueError('Use a formula or keyword parameters, never both')
    f = formula if formula is not None else Formula(**kwargs)
    if not isinstance(f, Formula): raise ValueError('Expected frozen Formula')
    bars, score, valid = formula_scores(minutes, f)
    signals: list[Signal] = []
    last_entry = -f.cooldown
    # An event is a score crossing its threshold from a no-signal state;
    # continuous strongly positive scores do not generate one trade per bar.
    last_side = 0
    for i in range(len(score)):
        side = (1 if score[i] > f.threshold else
                -1 if score[i] < -f.threshold else 0) if valid[i] else 0
        if not side:
            last_side = 0
            continue
        if side != last_side and i - last_entry >= f.cooldown:
            signals.append(Signal(
                confirmed_at=bars['close_at'].iloc[i],side=side,
                stop_distance=float(f.stop_usd),
                target_distance=float(f.stop_usd*f.reward_risk),
                strategy='arithmetic_'+f.identity()[:16],
            ))
            last_entry = i
        last_side = side
    return signals
