"""Synthetic shared-account replay of planned fills and observable M1 prices."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import math

import pandas as pd

from .lab_portfolio import _amount, _normalize_ledgers, _validate_position_limits

_MINUTE_NS = 60_000_000_000
_OPEN_EXITS = {'open_stop', 'open_target', 'gap_stop', 'time_exit'}
_CLOSE_EXITS = {'stop', 'target', 'ambiguous_stop_first', 'end_of_data'}


def _normalize_contracts(contracts, symbols):
    if type(contracts) is not dict or set(contracts) != symbols:
        raise ValueError('Require one explicit synthetic contract per ledger symbol')
    normalized = {}
    required = {'multiplier', 'initial_margin_rate'}
    with_maintenance = required | {'maintenance_margin_rate'}
    for symbol, contract in sorted(contracts.items()):
        if type(contract) is not dict or set(contract) not in (required, with_maintenance):
            raise ValueError('Contract requires multiplier and initial_margin_rate; maintenance_margin_rate is optional')
        multiplier = _amount(contract['multiplier'], 'contract multiplier', positive=True)
        rate = _amount(contract['initial_margin_rate'], 'initial margin rate', positive=True)
        if rate > 1.0:
            raise ValueError('Initial margin rate must be in (0, 1]')
        normalized[symbol] = {'multiplier': multiplier, 'initial_margin_rate': rate}
        if 'maintenance_margin_rate' in contract:
            maintenance = _amount(contract['maintenance_margin_rate'],
                                  'maintenance margin rate', positive=True)
            if maintenance > rate:
                raise ValueError('Maintenance margin rate must not exceed initial margin rate')
            normalized[symbol]['maintenance_margin_rate'] = maintenance
    if len({'maintenance_margin_rate' in contract for contract in normalized.values()}) > 1:
        raise ValueError('Maintenance margin requires an explicit rate for each symbol')
    return normalized


def _price_events(fixtures, symbols):
    if type(fixtures) is not dict or set(fixtures) != symbols:
        raise ValueError('Require one M1 fixture per ledger symbol')
    open_prices, close_prices = defaultdict(dict), defaultdict(dict)
    total_bars = 0
    for symbol, frame in sorted(fixtures.items()):
        if (not isinstance(frame, pd.DataFrame) or frame.empty
                or frame.columns.has_duplicates or not {'o', 'c'} <= set(frame)):
            raise ValueError('Each M1 fixture must have unique open and close columns')
        index = frame.index
        if (not isinstance(index, pd.DatetimeIndex) or str(index.tz) != 'UTC'
                or index.hasnans or index.has_duplicates or not index.is_monotonic_increasing):
            raise ValueError('Fixture requires sorted unique UTC M1 open times')
        total_bars += len(frame)
        if total_bars > 50000:
            raise ValueError('Portfolio replay supports at most 50000 supplied M1 bars')
        try:
            times = index.as_unit('ns').asi8
        except (ValueError, OverflowError) as exc:
            raise ValueError('M1 fixture timestamps must fit nanoseconds') from exc
        for timestamp, opening, closing in zip(times, frame['o'], frame['c']):
            start = int(timestamp)
            if start % _MINUTE_NS or start > pd.Timestamp.max.value - _MINUTE_NS:
                raise ValueError('Fixture marks must align to representable UTC minutes')
            open_prices[start][symbol] = _amount(opening, 'M1 opening mark', positive=True)
            close_prices[start + _MINUTE_NS][symbol] = _amount(closing, 'M1 closing mark', positive=True)
    return open_prices, close_prices


def _trade_events(trades, ledgers, contracts, open_prices, close_prices):
    entries, exits = defaultdict(list), defaultdict(list)
    for entry_ns, symbol, _, source_row, close_ns, trade in trades:
        if close_ns <= entry_ns:
            raise ValueError('Marked replay requires strictly later closure availability')
        opening = open_prices.get(entry_ns, {}).get(symbol)
        if opening is None or not math.isclose(opening, trade['entry_price'], rel_tol=1e-12):
            raise ValueError('Planned entry must match an observed fixture open')
        reason = ledgers[symbol][source_row].get('exit_reason', 'time_exit')
        if type(reason) is not str or reason not in _OPEN_EXITS | _CLOSE_EXITS:
            raise ValueError('Unknown planned exit availability phase')
        phase = 'bar_close' if reason in _CLOSE_EXITS else 'bar_open'
        phase_prices = close_prices if phase == 'bar_close' else open_prices
        if symbol not in phase_prices.get(close_ns, {}):
            raise ValueError('Planned closure must match an available fixture boundary')

        contract = contracts[symbol]
        units = trade['ounces'] * contract['multiplier']
        gross = trade['side'] * (trade['exit_price'] - trade['entry_price']) * units
        cost = trade['cost'] * contract['multiplier']
        order = dict(
            trade,
            exit_reason=reason,
            closure_phase=phase,
            contract_multiplier=contract['multiplier'],
            contract_units=units,
            initial_margin_rate=contract['initial_margin_rate'],
            entry_margin=opening * units * contract['initial_margin_rate'],
            supplied_gross_pnl=trade['gross_pnl'],
            supplied_net_pnl=trade['net_pnl'],
            supplied_cost=trade['cost'],
            gross_pnl=gross,
            cost=cost,
            net_pnl=gross - cost,
        )
        if 'maintenance_margin_rate' in contract:
            order['maintenance_margin_rate'] = contract['maintenance_margin_rate']
        entries[entry_ns].append(order)
        exits[(close_ns, phase)].append(order['trade_id'])
    return entries, exits


@dataclass(frozen=True)
class _Account:
    floating: float
    equity: float
    used_margin: float
    available_margin: float
    maintenance_margin: float


def _account(cash, active, prices):
    floating = math.fsum(
        trade['side'] * (prices[trade['symbol']] - trade['entry_price']) * trade['contract_units']
        - trade['cost']
        for trade in active.values()
    )
    used_margin = math.fsum(
        prices[trade['symbol']] * trade['contract_units'] * trade['initial_margin_rate']
        for trade in active.values()
    )
    maintenance = math.fsum(
        prices[trade['symbol']] * trade['contract_units'] * trade.get('maintenance_margin_rate', 0)
        for trade in active.values()
    )
    equity = cash + floating
    return _Account(floating, equity, used_margin, equity - used_margin, maintenance)


def replay_margin_portfolio(ledgers, fixtures, contracts, *, max_positions=2,
                            max_per_symbol=1, daily_loss_limit=1000.0,
                            initial_cash=10000.0):
    """Apply shared margin and daily equity limits to planned synthetic fills.

    Open/close marks become available at their respective M1 boundaries. At each
    timestamp, process the preceding close and its planned exits, then the
    current open and its planned exits, then new entries in stable order.
    Missing marks carry the last observed price. Midnight starts a new loss
    budget from the last observed equity before the first event of the new day.
    Fees reserve equity while a position is open and settle once at its exit.
    A loss breach locks admission for that UTC day. Explicit maintenance rates
    enable liquidation of positions with a fresh boundary price when account
    equity falls below the aggregate maintenance requirement.
    """
    _validate_position_limits(max_positions, max_per_symbol)
    cash = initial_cash = _amount(initial_cash, 'initial cash', positive=True)
    loss_limit = _amount(daily_loss_limit, 'daily loss limit', positive=True)
    trades = _normalize_ledgers(ledgers)
    symbols = set(ledgers)
    contracts = _normalize_contracts(contracts, symbols)
    open_prices, close_prices = _price_events(fixtures, symbols)
    entries, exits = _trade_events(trades, ledgers, contracts, open_prices, close_prices)

    active, prices = {}, {}
    active_by_symbol = defaultdict(int)
    accepted, rejected, observations, settlements, liquidations = [], [], [], [], []
    daily_net = defaultdict(float)
    daily_equity_change = {}
    halted_days = set()
    per_symbol = {symbol: 0.0 for symbol in sorted(symbols)}
    day = None
    day_start_equity = last_equity = peak_equity = peak_cash = initial_cash
    max_drawdown = max_realized_drawdown = peak_margin = total_fees = 0.0
    min_free_margin = initial_cash
    peak_positions = margin_deficit_events = 0
    maintenance_enabled = all('maintenance_margin_rate' in contract for contract in contracts.values())
    maintenance_breach_events = deferred_maintenance_events = 0

    def observe(at, phase):
        nonlocal last_equity, peak_equity, max_drawdown, peak_margin
        nonlocal min_free_margin, margin_deficit_events
        account = _account(cash, active, prices)
        change = account.equity - day_start_equity
        daily_equity_change[day] = change
        if change <= -loss_limit:
            halted_days.add(day)
        last_equity = account.equity
        peak_equity = max(peak_equity, account.equity)
        drawdown = peak_equity - account.equity
        max_drawdown = max(max_drawdown, drawdown)
        peak_margin = max(peak_margin, account.used_margin)
        min_free_margin = min(min_free_margin, account.available_margin)
        margin_deficit_events += int(account.available_margin < 0)
        observations.append({
            'at': at, 'phase': phase, 'cash': cash, 'floating_pnl': account.floating,
            'equity': account.equity, 'used_margin': account.used_margin,
            'available_margin': account.available_margin,
            'maintenance_margin': account.maintenance_margin,
            'drawdown': drawdown, 'daily_equity_change': change,
            'daily_halt': day in halted_days, 'open_positions': len(active),
        })

    def settle_batch(batch, at, phase, settlement_type):
        nonlocal cash, total_fees, peak_cash, max_realized_drawdown
        if not batch:
            return
        for trade in batch:
            del active[trade['trade_id']]
            active_by_symbol[trade['symbol']] -= 1
            per_symbol[trade['symbol']] += trade['net_pnl']
        net = math.fsum(trade['net_pnl'] for trade in batch)
        fees = math.fsum(trade['cost'] for trade in batch)
        cash += net
        total_fees += fees
        daily_net[day] += net
        peak_cash = max(peak_cash, cash)
        drawdown = peak_cash - cash
        max_realized_drawdown = max(max_realized_drawdown, drawdown)
        settlements.append({
            'at': at, 'phase': phase, 'settlement_type': settlement_type,
            'cash': cash, 'net_pnl': net, 'fees': fees,
            'closed_trades': len(batch), 'drawdown': drawdown,
        })

    def liquidate_at_fresh_marks(at, phase, updates):
        nonlocal maintenance_breach_events, deferred_maintenance_events
        if not maintenance_enabled or not active:
            return
        account = _account(cash, active, prices)
        if account.equity >= account.maintenance_margin:
            return
        maintenance_breach_events += 1
        fresh_positions = [trade for trade in active.values() if trade['symbol'] in updates]
        for trade in fresh_positions:
            planned = {key: trade[key] for key in (
                'closed_at', 'exit_price', 'exit_reason', 'closure_phase', 'gross_pnl', 'net_pnl',
            )}
            exit_price = updates[trade['symbol']]
            gross = trade['side'] * (exit_price - trade['entry_price']) * trade['contract_units']
            trade.update(planned_exit=planned, closed_at=at, exit_price=exit_price,
                         exit_reason='maintenance_liquidation', closure_phase=phase,
                         gross_pnl=gross, net_pnl=gross - trade['cost'])
            liquidations.append({
                'trade_id': trade['trade_id'], 'symbol': trade['symbol'],
                'at': at, 'phase': phase, 'exit_price': exit_price,
                'net_pnl': trade['net_pnl'], 'equity_before': account.equity,
                'maintenance_margin_before': account.maintenance_margin,
            })
        settle_batch(fresh_positions, at, phase, 'maintenance_liquidation')
        if active:
            remaining = _account(cash, active, prices)
            deferred_maintenance_events += int(remaining.equity < remaining.maintenance_margin)

    for instant in sorted(open_prices.keys() | close_prices.keys()):
        timestamp = pd.Timestamp(instant, unit='ns', tz='UTC')
        utc_day = timestamp.date().isoformat()
        if utc_day != day:
            day = utc_day
            day_start_equity = last_equity
        at = timestamp.isoformat()
        for phase, events in (('bar_close', close_prices), ('bar_open', open_prices)):
            updates = events.get(instant)
            if updates:
                prices.update(updates)
                planned_exits = [active[trade_id] for trade_id in exits.get((instant, phase), ())
                                 if trade_id in active]
                settle_batch(planned_exits, at, phase, 'planned_exit')
                liquidate_at_fresh_marks(at, phase, updates)
                observe(at, phase)

        accepted_before = len(accepted)
        for trade in entries.get(instant, ()):
            account = _account(cash, active, prices)
            free = account.available_margin
            symbol = trade['symbol']
            projected_equity = account.equity - trade['cost']
            if day in halted_days:
                reason = 'daily_loss_halt'
            elif len(active) >= max_positions:
                reason = 'shared_capacity'
            elif active_by_symbol[symbol] >= max_per_symbol:
                reason = 'symbol_capacity'
            elif free < trade['entry_margin'] + trade['cost']:
                reason = 'insufficient_margin'
            elif projected_equity - day_start_equity <= -loss_limit:
                reason = 'projected_daily_equity_loss'
            else:
                reason = None
            if reason:
                rejected.append(dict(trade, reason=reason, available_margin_before=free))
            else:
                accepted_trade = dict(trade, available_margin_before=free)
                accepted.append(accepted_trade)
                active[trade['trade_id']] = accepted_trade
                active_by_symbol[symbol] += 1
                peak_positions = max(peak_positions, len(active))
        if len(accepted) > accepted_before:
            observe(at, 'post_admission')

    if active:
        raise RuntimeError('Validated planned closures did not settle all accepted positions')
    net_total = math.fsum(trade['net_pnl'] for trade in accepted)
    return {
        'schema': 'NRFX_SYNTHETIC_MARGIN_PORTFOLIO_V1',
        'provenance': 'SUPPLIED_SYNTHETIC_FILLS_AND_M1_MARKS',
        'market_data_accessed': False,
        'live_trading_enabled': False,
        'contracts': contracts,
        'policy': {
            'max_positions': max_positions, 'max_per_symbol': max_per_symbol,
            'daily_loss_limit': loss_limit, 'initial_cash': initial_cash,
            'entry_priority': 'UTC_entry_then_symbol_then_strategy_then_source_row',
            'closures_before_same_time_entries': True,
            'same_timestamp_order': ['previous_close_and_exits', 'current_open_and_exits', 'entries'],
            'cost_recognition': 'scaled_roundtrip_fee_reserved_while_open_settled_at_exit',
            'margin_model': 'observable_price_times_contract_units_times_initial_margin_rate',
            'daily_loss_halt': 'sticky_UTC_day_observed_equity_from_pre_day_event_baseline',
            'missing_price_policy': 'carry_last_observed_mark',
            'maintenance_liquidation_enabled': maintenance_enabled,
            'maintenance_liquidation_policy': 'all_positions_with_fresh_phase_prices_after_planned_exits',
        },
        'accepted': accepted,
        'rejected': rejected,
        'per_symbol_net': per_symbol,
        'equity_at_closure': settlements,
        'equity_at_mark': observations,
        'maintenance_liquidations': liquidations,
        'daily_net': dict(sorted(daily_net.items())),
        'daily_equity_change': daily_equity_change,
        'daily_loss_halt_days': sorted(halted_days),
        'daily_equity_halt_days': sorted(halted_days),
        'summary': {
            'supplied_trades': len(trades), 'accepted_trades': len(accepted),
            'rejected_trades': len(rejected), 'net_pnl': net_total,
            'total_fees': total_fees, 'initial_cash': initial_cash, 'final_cash': cash,
            'max_realized_drawdown': max_realized_drawdown, 'peak_positions': peak_positions,
            'final_equity': last_equity, 'max_floating_drawdown': max_drawdown,
            'peak_used_margin': peak_margin, 'min_available_margin': min_free_margin,
            'margin_deficit_events': margin_deficit_events,
            'margin_rejections': sum(trade['reason'] == 'insufficient_margin' for trade in rejected),
            'maintenance_breach_events': maintenance_breach_events,
            'deferred_maintenance_breach_events': deferred_maintenance_events,
            'maintenance_liquidation_count': len(liquidations),
        },
        'limitations': [
            'Supplied synthetic execution fills and separate observed M1 boundary marks',
            'Equity uses the last observed mark through quote gaps',
            'A daily loss halt locks admissions for the rest of the UTC day',
            'Maintenance exits use fresh M1 boundary prices and the supplied roundtrip fee',
            'Remaining exit fills and rejected paths come from standalone candidate runs',
        ],
    }
