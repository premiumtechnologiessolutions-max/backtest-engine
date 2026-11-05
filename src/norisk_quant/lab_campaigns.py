"""Synthetic discovery, two-asset replay and Quantum selection orchestration.

Uses the project's existing Signal and execution kernels. All generated prices
and specifications are construction fixtures, never a new market data source.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

import numpy as np
import pandas as pd

from .execution import run
from .fast_engine import run_fast
from .lab_discovery import generate_specs, diagnose_candidates, signals_for_spec
from .lab_margin import replay_margin_portfolio
from .model import Settings
from .quantum_backends import solve_problem
from .quantum_selection import compile_selection


def _compact_portfolio(report):
    """Bound database output while binding the entire replay by digest."""
    encoded = json.dumps(report, sort_keys=True, separators=(',', ':'), allow_nan=False)
    compact = dict(report)
    compact['full_replay_sha256'] = hashlib.sha256(encoded.encode()).hexdigest()
    for field in ('accepted', 'rejected', 'equity_at_closure', 'equity_at_mark',
                  'maintenance_liquidations'):
        if isinstance(report.get(field), list):
            compact[field] = report[field][:40]
            compact[field + '_total'] = len(report[field])
            compact[field + '_truncated'] = len(report[field]) > 40
    return compact


def normalize_canonical_ledger(trades, strategy):
    """Map M1 intrabar candle labels to first knowable closure time."""
    result = []
    intrabar = {'stop','target','ambiguous_stop_first','end_of_data'}
    opening = {'open_stop','open_target','gap_stop','time_exit'}
    for original in trades.to_dict(orient='records'):
        row = dict(original)
        reason = row['exit_reason']
        if reason not in intrabar | opening:
            raise ValueError('Unknown closure availability contract')
        row['strategy'] = strategy
        row['source_candle_closed_at'] = row['closed_at'].isoformat()
        if reason in intrabar:
            row['closed_at'] = row['closed_at'] + pd.Timedelta(minutes=1)
        for name in ('entry_at','closed_at','signal_at'):
            row[name] = row[name].isoformat()
        result.append(row)
    return result


def run_discovery_campaign(spec, progress=lambda stage: None):
    # Local import avoids circular dependency and reuses the fixture/strict
    # complete ledger reconciliation from the original integrated coordinator.
    from .lab_coordinator import synthetic_fixture, _frame_digest, _parity
    progress('discovery_fixture')
    fixtures = {'SIM_A': synthetic_fixture(spec['bars'], spec['seed']),
                'SIM_B': synthetic_fixture(spec['bars'], spec['seed'] ^ 0xA5A5A5A5) * .6}
    settings = {'SIM_A': Settings(ounces=1., roundtrip_cost_per_ounce=.4, max_holding_minutes=60),
                'SIM_B': Settings(ounces=1., roundtrip_cost_per_ounce=.1, max_holding_minutes=45)}
    contracts = {
        'SIM_A': {'multiplier': 1., 'initial_margin_rate': .10, 'maintenance_margin_rate': .05},
        'SIM_B': {'multiplier': 2., 'initial_margin_rate': .15, 'maintenance_margin_rate': .075},
    }
    sources = {symbol: _frame_digest(frame) for symbol, frame in fixtures.items()}
    summaries, increments, inputs, all_ledgers, feedbacks = [], [], [], {}, []
    proposals = generate_specs(seed=spec['seed'], generation=0, count=4)
    for generation in range(2):
        records = []
        for candidate_no, candidate in enumerate(proposals):
            combined_net, combined_trades, combined_dd = 0., 0, 0.
            for symbol, minutes in fixtures.items():
                progress(f'g{generation}_{symbol.lower()}_candidate{candidate_no}')
                ident = symbol.lower() + '_' + candidate['id']
                signals = list(signals_for_spec(minutes, candidate))
                reference = run(minutes, signals, settings[symbol])
                fast = run_fast(minutes, signals, settings[symbol])
                _parity(reference, fast)
                equity = reference.equity['equity']
                delta = equity.diff()
                delta.iloc[0] = equity.iloc[0]
                dd = float((equity.cummax().clip(lower=0)-equity).clip(lower=0).max())
                net = float(equity.iloc[-1])
                scaled_delta = delta.to_numpy() * contracts[symbol]['multiplier']
                inputs.append({'id': ident, 'expected_return': float(scaled_delta.mean()),
                               'source_id': sources[symbol]})
                increments.append(scaled_delta)
                ledger = normalize_canonical_ledger(reference.trades, ident)
                all_ledgers[ident] = (symbol, ledger)
                summaries.append({'id': ident, 'symbol': symbol, 'spec': candidate,
                    'generation': generation, 'family': candidate['family'], 'parameters': candidate['parameters'],
                    'signals': len(signals), 'trades': len(ledger), 'net_usd_per_oz': net,
                    'max_drawdown_usd_per_oz': dd, 'units': 'invented_fixture_cash_units',
                    'parity_passed': True, 'trade_ledger_sha256': _frame_digest(reference.trades),
                    'equity_sha256': _frame_digest(reference.equity),
                    'curve': [float(x) for x in equity.iloc[::max(1,len(equity)//80)]]})
                combined_net += net
                combined_trades += len(ledger)
                # Diagnostic bound only, not a shared portfolio drawdown.
                combined_dd += dd
            records.append({'spec': candidate, 'trades': combined_trades,
                            'net_usd_per_oz': combined_net, 'max_drawdown_usd_per_oz': combined_dd,
                            'parity_passed': True})
        progress('discovery_feedback')
        feedback = diagnose_candidates(records, seed=(spec['seed'] + generation) % 2**32, count=4)
        feedbacks.append(feedback)
        proposals = feedback['proposals']
    progress('compile_multiasset_selection')
    compilation = compile_selection(inputs, np.cov(np.asarray(increments), ddof=1).tolist(),
                                    spec['select_count'], provenance='synthetic', source_ids=tuple(sources.values()))
    progress('quantum_multiasset_selection')
    selection = solve_problem(compilation.problem, backend=spec['backend'], layers=spec['layers'],
                              evaluations=spec['evaluations'], seed=spec['seed'], device=spec.get('device'))
    progress('shared_margin_portfolio')
    def replay(chosen):
        ledgers = {symbol: [] for symbol in fixtures}
        for ident in chosen:
            symbol, rows = all_ledgers[ident]
            ledgers[symbol].extend(rows)
        return _compact_portfolio(replay_margin_portfolio(
            ledgers, fixtures, contracts, max_positions=2, max_per_symbol=1,
            daily_loss_limit=20., initial_cash=10000.))
    quantum_portfolio = replay(selection['selected'])
    classic_portfolio = replay(selection['classical_exact_selected'])
    return {'schema': 'NRFX_SYNTHETIC_DISCOVERY_PORTFOLIO_V1',
            'provenance': 'SYNTHETIC_NOT_MARKET', 'market_data_accessed': False,
            'live_trading_enabled': False, 'candidates': summaries,
            'fixture_sha256': sources, 'instrument_settings': {k:asdict(v) for k,v in settings.items()},
            'selection': selection, 'compilation': compilation.manifest,
            'discovery': {'generations':2, 'evaluated':len(summaries),
                'distinct_specs':8, 'failure_analysis':feedbacks, 'next_proposals':proposals},
            'portfolio': quantum_portfolio, 'classical_portfolio':classic_portfolio,
            'stages':['discovery_fixture','two_generation_canonical_parity','discovery_feedback',
                      'compile_multiasset_selection','quantum_multiasset_selection','shared_margin_portfolio'],
            'limitations':['All OHLC and instrument contracts are invented construction fixtures',
                'Selection and generation share the same fixture, not independent validation',
                'Shared margin and floating equity are observed at M1 boundaries; planned exits are retained',
                'Candidate diagnostic drawdown totals are not portfolio drawdown',
                'QUBO optimum need not maximize the capacity-constrained realized portfolio result']}
