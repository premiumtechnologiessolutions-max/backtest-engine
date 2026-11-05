"""Causal shared-capacity replay of supplied synthetic closed-trade ledgers.

This is an admission/realized-cash construction model, not an intrabar portfolio
or broker execution simulator. Only invented SIM_* instrument labels are allowed.
No market files are opened and no cost model is inferred for real instruments.
"""
from __future__ import annotations

from collections import defaultdict
import heapq
import math
from numbers import Integral, Real
import re

import pandas as pd

_SYMBOL = re.compile(r'SIM_[A-Z0-9_]{1,40}\Z')
_REQUIRED = {'entry_at', 'closed_at', 'side', 'entry_price', 'exit_price',
             'ounces', 'gross_pnl', 'cost', 'net_pnl', 'strategy'}


def _amount(value, name, *, positive=False, nonnegative=False):
    if (isinstance(value, bool) or not isinstance(value, Real)
            or not math.isfinite(value) or abs(value) > 1e12
            or (positive and value <= 0) or (nonnegative and value < 0)):
        raise ValueError(f'Invalid finite bounded {name}')
    return float(value)


def _timestamp(value):
    if not isinstance(value, (str, pd.Timestamp)):
        raise ValueError('Trade timestamps must be explicit timezone-aware strings or Timestamp values')
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is None:
            raise ValueError('Naive or missing timestamp')
        return stamp.tz_convert('UTC').as_unit('ns')
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError('Invalid UTC trade timestamp') from exc


def replay_shared_portfolio(ledgers, *, max_positions=2, max_per_symbol=1,
                            daily_loss_limit=1000.0, initial_cash=10000.0):
    """Replay entry admission and grouped closures without future-P/L ranking.

    All exits at a timestamp settle as a batch before entries at that instant.
    Same-time entries use symbol/strategy/source-row priority, never future P/L.
    Daily loss halts are sticky until the next UTC date; already admitted trades
    continue to their supplied closures. Supplied closed_at must be the actual closure-availability instant,
    not an M1 candle label for an intrabar fill. Cost is an explicitly supplied
    total recognized at closure. No margin, exposure sizing or floating loss is modeled.
    """
    if type(ledgers) is not dict or not 1 <= len(ledgers) <= 64:
        raise ValueError('Require 1..64 supplied synthetic instrument ledgers')
    if (type(max_positions) is not int or not 1 <= max_positions <= 64
            or type(max_per_symbol) is not int or not 1 <= max_per_symbol <= 64):
        raise ValueError('Invalid shared position limits')
    initial_cash = _amount(initial_cash, 'initial cash', positive=True)
    loss_limit = _amount(daily_loss_limit, 'daily loss limit', positive=True)
    if any(type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
           or type(rows) is not list for symbol, rows in ledgers.items()):
        raise ValueError('Only synthetic SIM_* symbols and trade lists are accepted')
    trades = []
    for symbol, rows in sorted(ledgers.items()):
        if type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None or type(rows) is not list:
            raise ValueError('Only synthetic SIM_* symbols and trade lists are accepted')
        if len(trades) + len(rows) > 20000:
            raise ValueError('Portfolio replay supports at most 20000 supplied trades')
        for index, row in enumerate(rows):
            if type(row) is not dict or not _REQUIRED <= set(row):
                raise ValueError('Incomplete supplied trade accounting')
            entry, closed = _timestamp(row['entry_at']), _timestamp(row['closed_at'])
            if closed < entry:
                raise ValueError('Trade closure precedes its entry')
            if (isinstance(row['side'], bool) or not isinstance(row['side'], Integral)
                    or row['side'] not in (-1, 1)):
                raise ValueError('Invalid trade side')
            if (type(row['strategy']) is not str or not 1 <= len(row['strategy']) <= 128
                    or any(ord(c) < 32 for c in row['strategy'])):
                raise ValueError('Invalid strategy identity')
            normalized = dict(symbol=symbol, trade_id=f'{symbol}:{index}',
                              strategy=row['strategy'], entry_at=entry.isoformat(),
                              closed_at=closed.isoformat(), side=int(row['side']))
            for field in ('entry_price', 'exit_price', 'ounces', 'gross_pnl', 'cost', 'net_pnl'):
                normalized[field] = _amount(row[field], field,
                    positive=field in {'entry_price', 'exit_price', 'ounces'}, nonnegative=field == 'cost')
            gross = normalized['side'] * (normalized['exit_price'] - normalized['entry_price']) * normalized['ounces']
            if (not math.isclose(normalized['gross_pnl'], gross, rel_tol=0, abs_tol=1e-7)
                    or not math.isclose(normalized['net_pnl'], gross-normalized['cost'], rel_tol=0, abs_tol=1e-7)):
                raise ValueError('Supplied gross/net/cost accounting is inconsistent')
            trades.append((entry.value, symbol, row['strategy'], index, closed.value, normalized))
    trades.sort(key=lambda item: item[:4])
    pending, accepted, rejected, marks = [], [], [], []
    active = defaultdict(int)
    per_symbol = {symbol: 0.0 for symbol in sorted(ledgers)}
    daily_net = defaultdict(float)
    halted_days = set()
    cash = peak_cash = initial_cash
    maximum_drawdown = total_fees = 0.0
    peak_positions = 0
    sequence = 0

    def settle(up_to):
        nonlocal cash, peak_cash, maximum_drawdown, total_fees
        while pending and pending[0][0] <= up_to:
            instant = pending[0][0]
            batch = []
            while pending and pending[0][0] == instant:
                _, _, trade = heapq.heappop(pending)
                batch.append(trade)
                active[trade['symbol']] -= 1
                per_symbol[trade['symbol']] += trade['net_pnl']
            # Simultaneous closures have no observable internal priority. Mark
            # their combined cash once, avoiding artificial intermediate loss.
            net = math.fsum(t['net_pnl'] for t in batch)
            fees = math.fsum(t['cost'] for t in batch)
            cash += net
            total_fees += fees
            day = pd.Timestamp(instant, unit='ns', tz='UTC').date().isoformat()
            daily_net[day] += net
            if daily_net[day] <= -loss_limit:
                halted_days.add(day)
            peak_cash = max(peak_cash, cash)
            maximum_drawdown = max(maximum_drawdown, peak_cash-cash)
            marks.append({'at': pd.Timestamp(instant, unit='ns', tz='UTC').isoformat(),
                          'cash': cash, 'net_pnl': net, 'fees': fees,
                          'closed_trades': len(batch), 'drawdown': peak_cash-cash})

    for entry_ns, symbol, _, _, close_ns, trade in trades:
        settle(entry_ns)
        day = pd.Timestamp(entry_ns, unit='ns', tz='UTC').date().isoformat()
        if day in halted_days:
            reason = 'daily_loss_halt'
        elif len(pending) >= max_positions:
            reason = 'shared_capacity'
        elif active[symbol] >= max_per_symbol:
            reason = 'symbol_capacity'
        else:
            reason = None
        if reason:
            rejected.append(dict(trade, reason=reason))
        else:
            accepted.append(trade)
            active[symbol] += 1
            sequence += 1
            heapq.heappush(pending, (close_ns, sequence, trade))
            peak_positions = max(peak_positions, len(pending))
    if pending:
        settle(max(item[0] for item in pending))
    net_total = math.fsum(t['net_pnl'] for t in accepted)
    return {
        'schema': 'NRFX_SYNTHETIC_SHARED_PORTFOLIO_V1',
        'provenance': 'SUPPLIED_SYNTHETIC_LEDGERS_NOT_MARKET',
        'market_data_accessed': False, 'live_trading_enabled': False,
        'policy': {'max_positions': max_positions, 'max_per_symbol': max_per_symbol,
                   'daily_loss_limit': loss_limit, 'initial_cash': initial_cash,
                   'entry_priority': 'UTC_entry_then_symbol_then_strategy_then_source_row',
                   'closures_before_same_time_entries': True,
                   'simultaneous_closures': 'batch_net_before_daily_halt',
                   'daily_loss_halt': 'sticky_UTC_closure_day',
                   'cost_recognition': 'supplied_total_cost_at_closure',
                   'closure_timestamp_contract': 'supplied_actual_event_availability_not_candle_open_label'},
        'accepted': accepted, 'rejected': rejected,
        'per_symbol_net': per_symbol, 'equity_at_closure': marks,
        'daily_net': dict(sorted(daily_net.items())),
        'daily_loss_halt_days': sorted(halted_days),
        'summary': {'supplied_trades': len(trades), 'accepted_trades': len(accepted),
                    'rejected_trades': len(rejected), 'net_pnl': net_total,
                    'total_fees': total_fees, 'initial_cash': initial_cash,
                    'final_cash': cash, 'max_realized_drawdown': maximum_drawdown,
                    'peak_positions': peak_positions},
        'limitations': ['Synthetic supplied trade replay; no original market data',
                        'Closure cash only; no floating equity or intrabar drawdown',
                        'Caller must map intrabar candle labels to actual closure availability',
                        'No margin, buying-power, price impact or broker-fill model',
                        'Rejected trades are not resimulated; accepted paths are supplied unchanged'],
    }
