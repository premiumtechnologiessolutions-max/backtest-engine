from copy import deepcopy
import unittest

from norisk_quant.lab_portfolio import replay_shared_portfolio


def trade(entry, closed, net=1.0, *, cost=.4, strategy='fixture'):
    return {'entry_at':entry,'closed_at':closed,'side':1,'entry_price':2000.,
            'exit_price':2000.+net+cost,'ounces':1.,'gross_pnl':net+cost,
            'cost':cost,'net_pnl':net,'strategy':strategy}


def at(time, day='2024-01-01'):
    return day+'T'+time+':00Z'


class SharedPortfolioTests(unittest.TestCase):
    def test_future_winner_does_not_change_earlier_admission(self):
        rows = {'SIM_A':[trade(at('00:00'),at('00:10'),1)],
                'SIM_B':[trade(at('00:01'),at('00:11'),2)]}
        first = replay_shared_portfolio(rows,max_positions=1)
        rows['SIM_B'][0] = trade(at('00:01'),at('00:11'),100000.)
        second = replay_shared_portfolio(rows,max_positions=1)
        self.assertEqual([x['trade_id'] for x in first['accepted']], ['SIM_A:0'])
        self.assertEqual([x['trade_id'] for x in second['accepted']], ['SIM_A:0'])
        self.assertEqual(second['summary']['net_pnl'],1)
        self.assertEqual(second['rejected'][0]['reason'],'shared_capacity')

    def test_exits_at_entry_free_capacity_and_same_time_priority_is_deterministic(self):
        rows = {'SIM_B':[trade(at('00:00'),at('00:01'),2)],
                'SIM_A':[trade(at('00:00'),at('00:01'),1),trade(at('00:01'),at('00:02'),3)]}
        result = replay_shared_portfolio(rows,max_positions=1)
        self.assertEqual([x['trade_id'] for x in result['accepted']], ['SIM_A:0','SIM_A:1'])
        self.assertEqual(result['summary']['final_cash'],10004)
        self.assertEqual(result['summary']['peak_positions'],1)

    def test_simultaneous_closures_settle_as_batch(self):
        rows = {'SIM_A':[trade(at('00:00'),at('00:10'),-10),trade(at('00:10'),at('00:11'),1)],
                'SIM_B':[trade(at('00:00'),at('00:10'),10)]}
        result = replay_shared_portfolio(rows,daily_loss_limit=5)
        self.assertEqual(result['summary']['accepted_trades'],3)
        self.assertEqual(result['equity_at_closure'][0]['closed_trades'],2)
        self.assertEqual(result['equity_at_closure'][0]['net_pnl'],0)
        self.assertEqual(result['daily_loss_halt_days'],[])
        self.assertEqual(result['summary']['max_realized_drawdown'],0)

    def test_loss_halt_uses_closure_day_and_resets_next_UTC_day(self):
        rows = {'SIM_A':[trade(at('23:58'),at('00:01','2024-01-02'),-10),
                         trade(at('00:02','2024-01-02'),at('00:03','2024-01-02'),100),
                         trade(at('00:00','2024-01-03'),at('00:01','2024-01-03'),3)]}
        result = replay_shared_portfolio(rows,daily_loss_limit=5)
        self.assertEqual([x['trade_id'] for x in result['accepted']], ['SIM_A:0','SIM_A:2'])
        self.assertEqual(result['rejected'][0]['reason'],'daily_loss_halt')
        self.assertEqual(result['daily_loss_halt_days'],['2024-01-02'])
        self.assertEqual(result['summary']['max_realized_drawdown'],10)

    def test_symbol_limit_and_empty_ledger(self):
        result = replay_shared_portfolio({'SIM_A':[trade(at('00:00'),at('00:10')),trade(at('00:01'),at('00:12'))],
                                          'SIM_B':[]},max_positions=2)
        self.assertEqual(result['rejected'][0]['reason'],'symbol_capacity')
        self.assertEqual(result['per_symbol_net']['SIM_B'],0)
        empty = replay_shared_portfolio({'SIM_A':[]})
        self.assertEqual(empty['summary']['final_cash'],10000)
        self.assertEqual(empty['equity_at_closure'],[])

    def test_malformed_accounting_and_market_label_rejected(self):
        base = trade(at('00:00'),at('00:01'))
        for changes in ({'net_pnl':float('nan')},{'cost':-.4},{'gross_pnl':123.},
                        {'side':True},{'entry_at':'2024-01-01T00:00'},
                        {'closed_at':at('00:00','2023-12-31')}):
            row = deepcopy(base)
            row.update(changes)
            with self.assertRaises(ValueError):
                replay_shared_portfolio({'SIM_A':[row]})
        with self.assertRaises(ValueError):
            replay_shared_portfolio({'XAUUSD':[base]})


if __name__ == '__main__':
    unittest.main()
