"""Bounded synthetic construction proposals using the existing causal grammar.

No eval, source files, market ingestion, self-reported acceptance or OOS access.
Feedback is descriptive synthetic evidence supplied by the canonical coordinator;
this module cannot certify the origin or profitability of supplied metrics.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import random
import re

from .math_discovery import Formula, arithmetic_signals
from .research_evolution import _formula, _mutate
from .strategy import ema_cross_signals

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_EMA_FIELDS = frozenset({'timeframe', 'fast', 'slow', 'atr_period', 'stop_atr', 'rr'})
_SPEC_FIELDS = frozenset({'id', 'family', 'parameters', 'generation', 'parent_id', 'identity', 'proposal_sha256'})
_SUMMARY_FIELDS = frozenset({'spec', 'id', 'family', 'parameters', 'generation', 'parent_id',
    'trades', 'net_usd_per_oz', 'max_drawdown_usd_per_oz', 'signals', 'parity_passed',
    'trade_ledger_sha256', 'equity_sha256', 'curve', 'positive_months'})
_EMA_OPTIONS = {'fast': (3, 5, 7, 9, 12), 'slow': (15, 21, 25, 35, 50),
                'atr_period': (5, 8, 14, 21), 'stop_atr': (.75, 1., 1.5, 2.),
                'rr': (1., 1.5, 2., 3.)}


def _digest(value):
    try:
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                         allow_nan=False).encode()).hexdigest()
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValueError('Require finite JSON values') from exc


def _bounded(value, lower, upper, name):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f'Invalid bounded {name}')
    return value


def _parameters(family, parameters):
    if type(parameters) is not dict:
        raise ValueError('Frozen parameter object required')
    if family == 'arithmetic':
        return asdict(_formula(parameters))
    if family != 'ema' or set(parameters) != _EMA_FIELDS or parameters['timeframe'] != 'M1':
        raise ValueError('Only explicit EMA M1 and canonical arithmetic proposals supported')
    for field in ('fast', 'slow', 'atr_period'):
        _bounded(parameters[field], 1, 240, field)
    if parameters['slow'] <= parameters['fast']:
        raise ValueError('EMA slow must exceed fast')
    result = dict(parameters)
    for field in ('stop_atr', 'rr'):
        value = parameters[field]
        if type(value) not in (int, float) or not math.isfinite(value) or not .1 <= value <= 10:
            raise ValueError('Invalid EMA risk parameter')
        result[field] = float(value)
    return result


def _spec(family, parameters, generation, parent_id):
    generation = _bounded(generation, 0, 1_000_000, 'generation')
    parameters = _parameters(family, parameters)
    if parent_id is not None and (type(parent_id) is not str or not re.fullmatch(r'(ema|arithmetic)_[0-9a-f]{16}', parent_id)):
        raise ValueError('Invalid parent identity')
    identity = (_formula(parameters).identity() if family == 'arithmetic'
                else _digest({'family': family, 'parameters': parameters}))
    result = {'id': family + '_' + identity[:16], 'family': family,
              'parameters': parameters, 'generation': generation,
              'parent_id': parent_id, 'identity': identity}
    result['proposal_sha256'] = _digest(result)
    return result


def validate_candidate(spec):
    if type(spec) is not dict or set(spec) != _SPEC_FIELDS:
        raise ValueError('Candidate must match the frozen proposal schema')
    rebuilt = _spec(spec['family'], spec['parameters'], spec['generation'], spec['parent_id'])
    if rebuilt != spec:
        raise ValueError('Candidate identity or lineage differs from frozen parameters')
    return rebuilt


def generate_specs(seed=0, generation=0, parents=None, count=4):
    """Propose distinct bounded hypotheses; parents contain specs, never scores."""
    _bounded(seed, 0, 2**32-1, 'seed')
    _bounded(generation, 0, 1_000_000, 'generation')
    _bounded(count, 1, 16, 'candidate count')
    if parents is None:
        parents = []
    if type(parents) is not list or len(parents) > 32:
        raise ValueError('Bounded ranked parent specs required')
    parents = [validate_candidate(parent) for parent in parents]
    if generation > 0 and not parents:
        raise ValueError('Later generations require explicit parents')
    if parents and (generation == 0 or any(parent['generation'] >= generation for parent in parents)):
        raise ValueError('Child generation must follow all parent generations')
    rng = random.Random(seed + generation * 1_000_003)
    seen = {parent['identity'] for parent in parents}
    proposals = []
    for attempt in range(count * 100):
        if len(proposals) == count:
            break
        if parents:
            # Rank order is fixed by the coordinator's diagnostics. Half of
            # proposals explore the full parent set, half the best two.
            pool = parents[:2] if attempt % 2 == 0 else parents
            parent = pool[rng.randrange(len(pool))]
            family, params = parent['family'], dict(parent['parameters'])
            if family == 'arithmetic':
                child, _ = _mutate(_formula(params), rng)
                params = asdict(child)
            else:
                field = rng.choice(list(_EMA_OPTIONS))
                params[field] = rng.choice([x for x in _EMA_OPTIONS[field] if x != params[field]])
            candidate = _spec(family, params, generation, parent['id'])
        elif attempt % 2 == 0:
            params = {'timeframe': 'M1', **{field: rng.choice(values) for field, values in _EMA_OPTIONS.items()}}
            candidate = _spec('ema', params, generation, None)
        else:
            params = asdict(Formula(lookback=rng.choice((8, 12, 20, 30)),
                feature_a=0, feature_b=2, feature_c=1, reverse=rng.randrange(2),
                threshold=rng.choice((.2, .3, .5)), stop_usd=rng.choice((1., 1.5, 2.)),
                reward_risk=1.5, cooldown=8))
            candidate = _spec('arithmetic', params, generation, None)
        if candidate['identity'] in seen:
            continue
        seen.add(candidate['identity'])
        proposals.append(candidate)
    if len(proposals) != count:
        raise ValueError('Bounded proposal space exhausted')
    return proposals


def signals_for_spec(minutes, spec):
    """Delegate to existing causal Signal builders; never execute a trade."""
    candidate = validate_candidate(spec)
    if candidate['family'] == 'ema':
        return ema_cross_signals(minutes, **candidate['parameters'])
    return arithmetic_signals(minutes, _formula(candidate['parameters']))


def diagnose_candidates(summaries, *, seed=0, count=4):
    """Describe coordinator-computed synthetic metrics and propose children.

    Required record keys: spec, trades, net_usd_per_oz,
    max_drawdown_usd_per_oz. No provided score or accepted flag is allowed.
    The ranking is a declared descriptive heuristic, not statistical evidence.
    """
    if type(summaries) is not list or not 1 <= len(summaries) <= 32:
        raise ValueError('Require 1..32 candidate summaries')
    _digest(summaries)  # Reject NaN/Infinity even in optional display fields.
    entries, seen = [], set()
    for record in summaries:
        if type(record) is not dict or set(record) - _SUMMARY_FIELDS or not {
                'spec', 'trades', 'net_usd_per_oz', 'max_drawdown_usd_per_oz'}.issubset(record):
            raise ValueError('Unexpected or incomplete canonical synthetic feedback')
        candidate = validate_candidate(record['spec'])
        identity = candidate['identity']
        if identity in seen:
            raise ValueError('Duplicate candidate feedback')
        seen.add(identity)
        _bounded(record['trades'], 0, 1_000_000, 'trade count')
        for field in ('net_usd_per_oz', 'max_drawdown_usd_per_oz'):
            value = record[field]
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1e12:
                raise ValueError('Invalid bounded synthetic performance metric')
        if record['max_drawdown_usd_per_oz'] < 0:
            raise ValueError('Drawdown cannot be negative')
        if 'parity_passed' in record and record['parity_passed'] is not True:
            raise ValueError('Unreconciled feedback cannot drive generation')
        for field in ('trade_ledger_sha256', 'equity_sha256'):
            if field in record and (type(record[field]) is not str or not _HEX.fullmatch(record[field])):
                raise ValueError('Invalid feedback artifact identity')
        if 'id' in record and record['id'] != candidate['id']:
            raise ValueError('Feedback belongs to a different proposal')
        net, dd, trades = float(record['net_usd_per_oz']), float(record['max_drawdown_usd_per_oz']), record['trades']
        reasons = []
        if trades == 0:
            reasons.append('NO_EXECUTED_TRADES')
        if trades < 10:
            reasons.append('LOW_SYNTHETIC_TRADE_COUNT')
        if net < 0:
            reasons.append('NEGATIVE_SYNTHETIC_NET_AFTER_COSTS')
        if dd > abs(net):
            reasons.append('DRAWDOWN_EXCEEDS_ABSOLUTE_SYNTHETIC_NET')
        entries.append({'id': candidate['id'], 'identity': identity,
                        'spec': candidate, 'failure_reasons': reasons,
                        'synthetic_score': net - .25*dd, 'trades': trades,
                        'net_usd_per_oz': net, 'max_drawdown_usd_per_oz': dd})
    entries.sort(key=lambda item: (item['trades'] == 0, -item['synthetic_score'], item['identity']))
    next_generation = max(item['spec']['generation'] for item in entries) + 1
    proposals = generate_specs(seed=seed, generation=next_generation,
                              parents=[entry['spec'] for entry in entries], count=count)
    payload = {'schema': 'NRFX_SYNTHETIC_DISCOVERY_FEEDBACK_V1',
               'provenance': 'SYNTHETIC_NOT_MARKET',
               'feedback_sha256': _digest(summaries),
               'ranking_policy': 'nonempty_first_then_net_minus_quarter_drawdown_then_identity',
               'rankings': [{key: value for key, value in item.items() if key != 'spec'} for item in entries],
               'diagnostics': [{'id': item['id'], 'failure_reasons': item['failure_reasons']} for item in entries],
               'proposals': proposals, 'next_generation': next_generation,
               'proposal_basis': 'DESCRIPTIVE_SYNTHETIC_MUTATION_NOT_CAUSAL_DISCOVERY',
               'feedback_origin_independently_attested': False,
               'independent_oos_proven': False, 'strategy_approved': False,
               'market_data_accessed': False}
    payload['manifest_sha256'] = _digest(payload)
    return payload
