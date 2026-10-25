import pandas as pd
import pytest
from norisk_quant.model import Signal
from norisk_quant.portfolio import PortfolioSettings, run_portfolio, validate_portfolio, write_portfolio_report


def bars(rows, times=None):
    if times is None:
        times = pd.date_range('2024-01-02T00:00:00Z', periods=len(rows), freq='min')
    return pd.DataFrame(rows, index=times, columns=['o','h','l','c'])


def test_two_strategies_share_equity_and_cost_once(tmp_path):
    market = bars([[100,100,100,100],[100,102,99,101],[101,101,100,100]])
    sigs = [Signal(market.index[1],1,1,2,'a'),Signal(market.index[1],-1,1,2,'b')]
    settings = PortfolioSettings({'a':1,'b':2}, max_open_positions=2, max_total_ounces=3)
    result = run_portfolio(market,sigs,settings)
    assert len(result.trades)==2
    assert result.trades['cost'].sum()==pytest.approx(1.2)
    assert result.trades['net_pnl'].sum()==pytest.approx(-3-1.2)
    assert result.equity['equity'].iloc[-1]==pytest.approx(-4.2)
    assert validate_portfolio(result,settings)['status']=='PASSED'
    summary=write_portfolio_report(result,settings,tmp_path)
    assert summary['trades']==2
    assert (tmp_path/'monthly.csv').exists()


def test_capacity_freeze_no_same_minute_recycling():
    market = bars([[100,100,100,100],[100,102,99,101],[100,100,100,100]])
    sigs = [Signal(market.index[0],1,1,5,'a'),Signal(market.index[1],1,1,5,'b')]
    settings = PortfolioSettings({'a':1,'b':1}, max_open_positions=1, max_total_ounces=1)
    result=run_portfolio(market,sigs,settings)
    assert len(result.trades)==1
    assert result.capacity_rejected==1
    assert result.trades.iloc[0]['strategy']=='a'


def test_gap_stop_and_shared_float():
    idx=pd.to_datetime(['2024-01-02T00:00:00Z','2024-01-02T00:01:00Z','2024-01-02T00:20:00Z'])
    market=bars([[100,100,100,100],[100,100.5,99.5,100],[96,97,95,96]],idx)
    settings=PortfolioSettings({'a':1},max_open_positions=1,max_total_ounces=1)
    result=run_portfolio(market,[Signal(idx[1],1,2,4,'a')],settings)
    assert result.trades.iloc[0]['exit_reason']=='gap_stop'
    assert result.trades.iloc[0]['exit_price']==96
    assert result.trades.iloc[0]['gap_minutes']==18
    assert result.trades.iloc[0]['net_pnl']==pytest.approx(-4.4)
    assert validate_portfolio(result,settings)['status']=='PASSED'


def test_reject_double_cost_or_bad_realized_timeline():
    idx=pd.date_range('2024-01-02T00:00:00Z',periods=2,freq='min')
    market=bars([[100,100,100,100],[100,101,99,100]],idx)
    settings=PortfolioSettings({'a':1},max_open_positions=1,max_total_ounces=1)
    result=run_portfolio(market,[Signal(idx[1],1,1,2,'a')],settings)
    result.trades.loc[0,'cost']=0.8
    with pytest.raises(ValueError,match='fee'):
        validate_portfolio(result,settings)
    result.trades.loc[0,'cost']=0.4
    result.equity.loc[idx[0],'realized_pnl']=1
    result.equity.loc[idx[0],'equity']=1
    with pytest.raises(ValueError,match='chronology'):
        validate_portfolio(result,settings)


def test_no_lookahead_and_reject_missing_allocation():
    idx=pd.date_range('2024-01-02T00:00:00Z',periods=2,freq='min')
    market=bars([[100,100,100,100],[100,100,100,100]],idx)
    settings=PortfolioSettings({'a':1},max_open_positions=1,max_total_ounces=1)
    result=run_portfolio(market,[Signal(idx[1]+pd.Timedelta(seconds=30),1,1,2,'a')],settings)
    assert result.trades.empty and result.pending_at_end==1
    with pytest.raises(ValueError,match='Missing allocation'):
        run_portfolio(market,[Signal(idx[0],1,1,2,'b')],settings)
    with pytest.raises(ValueError,match='fixes ALL-IN'):
        PortfolioSettings({'a':1},all_in_cost_per_ounce=0.8)


def test_monthly_realized_differs_from_mark_to_market_across_month_end(tmp_path):
    idx = pd.to_datetime([
        '2024-01-31T23:58:00Z', '2024-01-31T23:59:00Z',
        '2024-02-01T00:00:00Z', '2024-02-01T00:01:00Z',
    ])
    market = bars([[100,100,100,100],[100,101,100,101],
                   [101,103,101,103],[103,104,103,104]], idx)
    settings = PortfolioSettings({'a':1}, max_open_positions=1,max_total_ounces=1)
    result = run_portfolio(market, [Signal(idx[1],1,5,10,'a')], settings)
    write_portfolio_report(result,settings,tmp_path)
    monthly = pd.read_csv(tmp_path/'monthly.csv')
    assert len(monthly)==2
    assert monthly.loc[0,'trades']==0
    assert monthly.loc[0,'net_pnl']==0
    assert monthly.loc[0,'equity_change']==pytest.approx(0.6)
    assert monthly.loc[1,'trades']==1
    assert monthly.loc[1,'net_pnl']==pytest.approx(3.6)
    assert monthly.loc[1,'equity_change']==pytest.approx(3.0)
