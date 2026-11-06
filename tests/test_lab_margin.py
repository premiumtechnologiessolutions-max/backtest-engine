import unittest

import pandas as pd

from norisk_quant.lab_margin import replay_margin_portfolio


def fixture(start, openings, closings=None):
    return pd.DataFrame(
        {'o': openings, 'c': openings if closings is None else closings},
        index=pd.date_range(start, periods=len(openings), freq='min', tz='UTC'),
    )


def planned(frame, start, end, *, side=1, cost=0.0, reason='time_exit', exit_price=None):
    entry_price = float(frame['o'].iloc[start])
    if exit_price is None:
        exit_price = float(frame['o'].iloc[end])
    gross = side * (exit_price - entry_price)
    return {
        'entry_at': frame.index[start], 'closed_at': frame.index[end],
        'side': side, 'entry_price': entry_price, 'exit_price': exit_price,
        'ounces': 1.0, 'gross_pnl': gross, 'cost': cost,
        'net_pnl': gross - cost, 'strategy': 'fixture', 'exit_reason': reason,
    }


def contracts(multiplier_a=1.0, rate_a=0.25, rate_b=0.25):
    return {
        'SIM_A': {'multiplier': multiplier_a, 'initial_margin_rate': rate_a},
        'SIM_B': {'multiplier': 1.0, 'initial_margin_rate': rate_b},
    }


class MarginPortfolioTests(unittest.TestCase):
    def test_contract_multiplier_margin_competition_and_release(self):
        first = fixture('2024-01-01', [100.0, 104.0, 104.0])
        second = fixture('2024-01-01', [100.0, 100.0, 102.0])
        result = replay_margin_portfolio(
            {'SIM_B': [planned(second, 0, 1), planned(second, 1, 2)],
             'SIM_A': [planned(first, 0, 1, cost=1.0)]},
            {'SIM_A': first, 'SIM_B': second}, contracts(2.0, 0.4),
            initial_cash=100.0,
        )
        self.assertEqual([trade['trade_id'] for trade in result['accepted']], ['SIM_A:0', 'SIM_B:1'])
        self.assertEqual(result['rejected'][0]['reason'], 'insufficient_margin')
        self.assertEqual(result['rejected'][0]['available_margin_before'], 18.0)
        self.assertEqual(result['summary']['margin_rejections'], 1)
        self.assertEqual(result['summary']['peak_used_margin'], 80.0)
        self.assertEqual(result['summary']['final_equity'], 108.0)
        self.assertEqual(result['summary']['total_fees'], 2.0)
        self.assertEqual(result['per_symbol_net'], {'SIM_A': 6.0, 'SIM_B': 2.0})

    def test_close_drawdown_latches_before_a_same_time_open_recovery(self):
        first = fixture('2024-01-01', [100.0, 101.0, 103.0], [93.0, 103.0, 103.0])
        second = fixture('2024-01-01', [100.0, 100.0, 100.0])
        result = replay_margin_portfolio(
            {'SIM_A': [planned(first, 0, 2)], 'SIM_B': [planned(second, 1, 2)]},
            {'SIM_A': first, 'SIM_B': second}, contracts(),
            initial_cash=100.0, daily_loss_limit=5.0,
        )
        marks = [mark for mark in result['equity_at_mark']
                 if mark['at'] == first.index[1].isoformat()]
        self.assertEqual([(mark['phase'], mark['equity']) for mark in marks],
                         [('bar_close', 93.0), ('bar_open', 101.0)])
        self.assertEqual(result['rejected'][0]['reason'], 'daily_loss_halt')
        self.assertEqual(result['daily_equity_halt_days'], ['2024-01-01'])
        self.assertEqual(result['summary']['max_floating_drawdown'], 7.0)
        self.assertEqual(result['summary']['max_realized_drawdown'], 0.0)
        self.assertEqual(result['summary']['final_equity'], 103.0)

    def test_current_bar_close_and_later_exit_cannot_select_open_entries(self):
        second = fixture('2024-01-01', [100.0, 101.0])
        first = fixture('2024-01-01', [100.0, 100.0])
        def replay(frame, price):
            return replay_margin_portfolio(
                {'SIM_A': [planned(frame, 0, 1, exit_price=price)],
                 'SIM_B': [planned(second, 0, 1)]},
                {'SIM_A': frame, 'SIM_B': second}, contracts(),
                initial_cash=60.0, daily_loss_limit=5.0,
            )
        baseline = replay(first, 100.0)
        adverse = replay(fixture('2024-01-01', [100.0, 100.0], [5.0, 100.0]), 5.0)
        self.assertEqual([row['trade_id'] for row in adverse['accepted']],
                         [row['trade_id'] for row in baseline['accepted']])
        self.assertEqual(adverse['equity_at_mark'][:2], baseline['equity_at_mark'][:2])
        self.assertGreater(adverse['summary']['margin_deficit_events'], 0)

    def test_intrabar_exits_batch_before_open_and_release_margin(self):
        first = fixture('2024-01-01', [100.0, 100.0, 100.0], [90.0, 100.0, 100.0])
        second = fixture('2024-01-01', [100.0, 100.0, 100.0], [110.0, 100.0, 100.0])
        result = replay_margin_portfolio(
            {'SIM_A': [planned(first, 0, 1, reason='stop', exit_price=90.0), planned(first, 1, 2)],
             'SIM_B': [planned(second, 0, 1, reason='target', exit_price=110.0)]},
            {'SIM_A': first, 'SIM_B': second}, contracts(rate_a=0.5, rate_b=0.5),
            initial_cash=100.0, daily_loss_limit=5.0,
        )
        self.assertEqual(result['summary']['accepted_trades'], 3)
        self.assertEqual(result['equity_at_closure'][0]['closed_trades'], 2)
        self.assertEqual(result['equity_at_closure'][0]['phase'], 'bar_close')
        self.assertEqual(result['daily_equity_halt_days'], [])

    def test_midnight_resets_admission_budget_with_carried_equity(self):
        first = fixture('2024-01-01T23:58', [100.0, 96.0, 94.0, 94.0], [96.0, 95.0, 94.0, 94.0])
        second = fixture('2024-01-01T23:58', [100.0, 100.0, 100.0, 100.0])
        result = replay_margin_portfolio(
            {'SIM_A': [planned(first, 0, 3)],
             'SIM_B': [planned(second, 1, 2), planned(second, 2, 3)]},
            {'SIM_A': first, 'SIM_B': second}, contracts(),
            initial_cash=100.0, daily_loss_limit=3.0,
        )
        self.assertEqual(result['daily_equity_halt_days'], ['2024-01-01'])
        self.assertEqual([row['trade_id'] for row in result['accepted']], ['SIM_A:0', 'SIM_B:1'])
        self.assertEqual(result['daily_equity_change']['2024-01-02'], -2.0)

    def test_maintenance_liquidation_uses_only_fresh_boundary_prices(self):
        first = fixture('2024-01-01', [100.0, 10.0, 10.0, 100.0, 110.0])
        second = fixture('2024-01-01', [100.0, 100.0, 100.0, 100.0, 110.0])
        sparse_second = second.drop(second.index[[1, 2]])
        rules = contracts(rate_a=0.5, rate_b=0.5)
        for contract in rules.values():
            contract['maintenance_margin_rate'] = 0.4
        result = replay_margin_portfolio(
            {'SIM_A': [planned(first, 0, 4, cost=0.5)],
             'SIM_B': [planned(second, 0, 4, cost=0.5)]},
            {'SIM_A': first, 'SIM_B': sparse_second}, rules, initial_cash=102.0,
        )
        liquidations = result['maintenance_liquidations']
        self.assertEqual([(row['symbol'], row['at'], row['exit_price']) for row in liquidations],
                         [('SIM_A', first.index[1].isoformat(), 10.0),
                          ('SIM_B', second.index[3].isoformat(), 100.0)])
        self.assertEqual(result['summary']['maintenance_liquidation_count'], 2)
        self.assertGreater(result['summary']['deferred_maintenance_breach_events'], 0)
        self.assertEqual(result['summary']['final_equity'], 11.0)
        self.assertEqual(result['summary']['net_pnl'], -91.0)
        self.assertEqual(result['summary']['total_fees'], 1.0)
        self.assertEqual(result['accepted'][0]['exit_reason'], 'maintenance_liquidation')
        self.assertEqual(result['accepted'][0]['planned_exit']['exit_price'], 110.0)
        self.assertEqual(result['accepted'][0]['planned_exit']['closed_at'], first.index[4].isoformat())

    def test_supplied_entry_and_close_boundaries_and_contracts_are_validated(self):
        frame = fixture('2024-01-01', [100.0, 100.0])
        valid = planned(frame, 0, 1)
        for change in (
            {'entry_price': 99.0, 'gross_pnl': 1.0, 'net_pnl': 1.0},
            {'closed_at': frame.index[1] + pd.Timedelta(seconds=1)},
            {'closed_at': frame.index[0]},
            {'exit_reason': 'unrecognized'},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replay_margin_portfolio(
                    {'SIM_A': [dict(valid, **change)], 'SIM_B': []},
                    {'SIM_A': frame, 'SIM_B': frame}, contracts(),
                )
        mixed = contracts()
        mixed['SIM_A']['maintenance_margin_rate'] = 0.1
        impossible = contracts()
        impossible['SIM_A']['maintenance_margin_rate'] = 0.3
        impossible['SIM_B']['maintenance_margin_rate'] = 0.1
        for bad_contracts in ({}, contracts(rate_a=1.1), contracts(multiplier_a=True), mixed, impossible):
            with self.subTest(contracts=bad_contracts), self.assertRaises(ValueError):
                replay_margin_portfolio(
                    {'SIM_A': [], 'SIM_B': []}, {'SIM_A': frame, 'SIM_B': frame}, bad_contracts,
                )
