"""FAC018 synthetic-only tests: no private market data or outcome inspection."""
import numpy as np
import pandas as pd
import pytest

from scripts import batch_session_inventory_h4_grid as fac


def m15_fixture(day='2012-01-03', session='LONDON_LOCAL_08_12'):
    idx = pd.date_range(day, periods=200, freq='15min', tz='UTC')
    n = len(idx)
    op = np.full(n, 100.)
    hi = np.full(n, 100.5)
    lo = np.full(n, 99.5)
    close = np.full(n, 100.)
    if session == 'LONDON_LOCAL_08_12':
        local = idx.tz_convert('Europe/London')
        event_clock = 10*60
    else:
        local = idx.tz_convert('America/New_York')
        event_clock = 11*60
    minute = np.asarray(local.hour*60+local.minute)
    jprev = int(np.flatnonzero(minute == event_clock)[0])
    j = jprev+1
    op[jprev], hi[jprev], lo[jprev], close[jprev] = 100., 103.5, 99.5, 103.
    op[j], hi[j], lo[j], close[j] = 102.5, 102.7, 100.8, 101.2
    return pd.DataFrame({'o':op, 'h':hi, 'l':lo, 'c':close,
                         'close_at':idx+pd.Timedelta(minutes=15)}, index=idx), j


def test_frozen_grid_cost_and_prereg():
    assert fac.TOTAL == fac.SPEC['specs_per_year'] == 9216
    assert fac.SPEC['preregistration_commit'] == fac.PREREG
    assert fac.SPEC['roundtrip_all_in_usd_oz'] == .4
    assert fac.SPEC['years'] == [2012, 2013]
    assert len(fac.H4_WINDOWS)*len(fac.EXCURSIONS)*len(fac.RETREATS)*len(fac.REGIMES)*len(fac.SESSIONS) == 144


@pytest.mark.parametrize('day,session', [
    ('2012-01-03', 'LONDON_LOCAL_08_12'),
    ('2012-01-03', 'NY_LOCAL_0930_1330'),
    ('2012-03-12', 'NY_LOCAL_0930_1330'),
])
def test_completed_session_anchor_and_dst(day, session):
    bars, j = m15_fixture(day, session)
    times, sides, bases = fac.session_inventory_signals(bars, 2., .4, session)
    expected = int(bars.close_at.iloc[j].timestamp())
    assert expected in times.tolist()
    ix = times.tolist().index(expected)
    assert sides[ix] == -1
    assert bases[ix] > 0
    early, _, _ = fac.session_inventory_signals(bars.iloc[:j], 2., .4, session)
    assert expected not in early.tolist()
    partial, partial_s, partial_b = fac.session_inventory_signals(bars.iloc[:j+1], 2., .4, session)
    assert np.array_equal(times[times <= expected], partial)
    assert np.array_equal(sides[:len(partial)], partial_s)
    assert np.array_equal(bases[:len(partial)], partial_b)


def test_session_gap_fails_closed():
    bars, j = m15_fixture()
    expected = int(bars.close_at.iloc[j].timestamp())
    assert expected in fac.session_inventory_signals(bars, 2., .4, 'LONDON_LOCAL_08_12')[0]
    missing = bars.drop(bars.index[j-3])
    assert expected not in fac.session_inventory_signals(missing, 2., .4, 'LONDON_LOCAL_08_12')[0]


def test_no_excursion_or_no_inward_candle():
    bars, j = m15_fixture()
    weak = bars.copy()
    weak.loc[weak.index[j-1], ['o','h','l','c']] = [100.,100.6,99.5,100.3]
    expected = int(bars.close_at.iloc[j].timestamp())
    assert expected not in fac.session_inventory_signals(weak, 2., .4, 'LONDON_LOCAL_08_12')[0]
    wrong = bars.copy()
    wrong.loc[wrong.index[j], ['o','h','l','c']] = [100.5,103.,100.5,102.8]
    assert expected not in fac.session_inventory_signals(wrong, 2., .4, 'LONDON_LOCAL_08_12')[0]


def test_h4_efficiency_contiguous_and_gap():
    idx = pd.date_range('2012-01-03', periods=8, freq='4h', tz='UTC')
    close = np.array([100., 101., 100., 101., 100., 101., 100., 101.])
    bars = pd.DataFrame({'c':close, 'close_at':idx+pd.Timedelta(hours=4)}, index=idx)
    times, eff = fac.completed_h4_efficiency(bars, 4)
    assert np.isnan(eff[2])
    assert eff[3] == pytest.approx(1/3)
    missing = bars.drop(bars.index[4])
    _, gap_eff = fac.completed_h4_efficiency(missing, 4)
    assert np.isnan(gap_eff[5])


def test_h4_regime_uses_last_completed_and_halts():
    times = np.array([10000, 14400, 18000, 28800, 32400, 50000], np.int64)
    sides = np.ones(len(times), np.int8)
    base = np.ones(len(times), float)
    h4times = np.array([14400, 28800], np.int64)
    eff = np.array([.2, .8])
    t, _, _ = fac.causal_h4_gate(times, sides, base, h4times, eff, 'RANGE')
    assert t.tolist() == [14400, 18000]
    t, _, _ = fac.causal_h4_gate(times, sides, base, h4times, eff, 'TRANSITION')
    assert len(t) == 0


@pytest.mark.parametrize('excursion,retreat,session', [
    (True,.4,'LONDON_LOCAL_08_12'),
    (2.,True,'LONDON_LOCAL_08_12'),
    (2.,.4,'ALL'),
    (1.3,.4,'LONDON_LOCAL_08_12'),
    (2.,.33,'LONDON_LOCAL_08_12'),
])
def test_nonfrozen_params_rejected(excursion, retreat, session):
    with pytest.raises(ValueError):
        fac.session_inventory_signals(m15_fixture()[0], excursion, retreat, session)


def test_non_utc_and_incomplete_m15_rejected():
    bars, _ = m15_fixture()
    naive = bars.copy()
    naive.index = naive.index.tz_localize(None)
    with pytest.raises(ValueError):
        fac.session_inventory_signals(naive, 2., .4, 'LONDON_LOCAL_08_12')
    broken = bars.copy()
    broken.loc[broken.index[25], 'close_at'] = broken.index[25]+pd.Timedelta(minutes=14)
    with pytest.raises(ValueError):
        fac.session_inventory_signals(broken, 2., .4, 'LONDON_LOCAL_08_12')


def test_frozen_year_limit_and_h4_window():
    with pytest.raises(ValueError):
        fac.run_batch(None, 2014, '/tmp/invalid-fac018')
    with pytest.raises(ValueError):
        fac.run_batch(None, 2012, '/tmp/invalid-fac018', 9217)
    with pytest.raises(ValueError):
        fac.run_batch(None, True, '/tmp/invalid-fac018')
    with pytest.raises(ValueError):
        fac.completed_h4_efficiency(pd.DataFrame(), True)


def test_canonical_signal_cost_not_double_counted():
    s = fac.canonical_signals(np.array([3600]), np.array([-1]), np.array([1.5]), 2., 1.)
    assert s[0].side == -1
    assert s[0].stop_distance == pytest.approx(3.)
    assert s[0].target_distance == pytest.approx(1.5)
