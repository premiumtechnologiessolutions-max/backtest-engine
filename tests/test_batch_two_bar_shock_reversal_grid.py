"""FAC017 synthetic-only frozen-grid, causality, gap, regime and risk tests."""
import numpy as np
import pandas as pd
import pytest

from scripts import batch_two_bar_shock_reversal_grid as fac


def m15_fixture(direction=1, shock_index=55, n=90):
    idx = pd.date_range('2012-01-02', periods=n, freq='15min', tz='UTC')
    op = np.full(n, 100.)
    hi = np.full(n, 100.5)
    lo = np.full(n, 99.5)
    close = np.full(n, 100.)
    j = shock_index
    if direction == 1:
        op[j], hi[j], lo[j], close[j] = 100., 103., 99., 102.7
        op[j+1], hi[j+1], lo[j+1], close[j+1] = 102., 102.5, 100., 100.5
    else:
        op[j], hi[j], lo[j], close[j] = 100., 101., 97., 97.3
        op[j+1], hi[j+1], lo[j+1], close[j+1] = 97.5, 100., 97.4, 99.5
    return pd.DataFrame({'o': op, 'h': hi, 'l': lo, 'c': close,
                         'close_at': idx+pd.Timedelta(minutes=15)}, index=idx)


def test_frozen_grid_count_cost_and_preoutcome_commit():
    assert fac.TOTAL == fac.SPEC['specs_per_year'] == 18432
    assert fac.SPEC['roundtrip_all_in_usd_oz'] == .4
    assert fac.SPEC['years'] == [2012, 2013]
    assert fac.SPEC['preregistration_commit'] == fac.PREREG
    assert len(fac.LOOKBACKS)*len(fac.SHOCKS)*len(fac.RETRACES)*len(fac.REGIMES)*len(fac.SESSIONS) == 288


@pytest.mark.parametrize('direction,expected', [(1, -1), (-1, 1)])
def test_two_bar_reversal_signal_only_at_completed_confirmation(direction, expected):
    bars = m15_fixture(direction)
    times, sides, bases = fac.shock_reversal_signals(bars, 12, 2., .4)
    expected_at = int(bars.close_at.iloc[56].timestamp())
    assert expected_at in times.tolist()
    k = times.tolist().index(expected_at)
    assert sides[k] == expected
    assert bases[k] == pytest.approx(1.)
    # No shock event may be entered at the shock close, before the reversal bar closes.
    early, _, _ = fac.shock_reversal_signals(bars.iloc[:56], 12, 2., .4)
    assert expected_at not in early.tolist()
    # Adding later data cannot change any earlier confirmed signals.
    t_short, s_short, b_short = fac.shock_reversal_signals(bars.iloc[:70], 12, 2., .4)
    assert np.array_equal(times[times < int(bars.close_at.iloc[70].timestamp())], t_short)
    assert np.array_equal(sides[:len(t_short)], s_short)
    assert np.array_equal(bases[:len(t_short)], b_short)


def test_gap_inside_lookback_rejects_shock_signal():
    bars = m15_fixture()
    assert int(bars.close_at.iloc[56].timestamp()) in fac.shock_reversal_signals(bars, 12, 2., .4)[0]
    missing = bars.drop(bars.index[50])
    times, _, _ = fac.shock_reversal_signals(missing, 12, 2., .4)
    assert int(bars.close_at.iloc[56].timestamp()) not in times


def test_shock_must_be_large_and_directional_and_retrace():
    bars = m15_fixture()
    weak = bars.copy()
    weak.loc[weak.index[55], ['o', 'h', 'l', 'c']] = [100., 100.8, 99.8, 100.7]
    assert int(bars.close_at.iloc[56].timestamp()) not in fac.shock_reversal_signals(weak, 12, 2., .4)[0]
    no_retrace = bars.copy()
    no_retrace.loc[no_retrace.index[56], ['o', 'h', 'l', 'c']] = [102.8, 103., 102., 102.2]
    assert int(bars.close_at.iloc[56].timestamp()) not in fac.shock_reversal_signals(no_retrace, 12, 2., .4)[0]


def test_h1_causal_regime_halt_and_age():
    times = np.array([3500, 7200, 10800, 14400, 18000, 21601], np.int64)
    sides = np.array([-1]*len(times), np.int8)
    base = np.ones(len(times))
    h1times = np.array([3600, 7200, 10800, 14400], np.int64)
    ratios = np.array([1., 1.5, 2.5, .8])
    masks = {'ALL': np.ones(len(times), dtype=bool)}
    q, _, _ = fac.causal_regime_session_gate(times, sides, base, h1times, ratios,
                                             'QUIET', 'ALL', masks)
    a, _, _ = fac.causal_regime_session_gate(times, sides, base, h1times, ratios,
                                             'ACTIVE', 'ALL', masks)
    assert q.tolist() == [14400, 18000]
    assert a.tolist() == [7200]
    assert 3500 not in q and 3500 not in a
    assert 10800 not in a  # pre-known >2.0 H1 volatility halt
    assert 21601 not in q  # stale H1, >1 hour


def test_h1_invalid_chronology_and_signal_sides_fail_closed():
    with pytest.raises(ValueError):
        fac.causal_regime_session_gate(np.array([100]), np.array([1]), np.array([1.]),
                                       np.array([100, 100]), np.array([1., 1.]),
                                       'QUIET', 'ALL')
    with pytest.raises(ValueError):
        fac.causal_regime_session_gate(np.array([100]), np.array([0]), np.array([1.]),
                                       np.array([100]), np.array([1.]),
                                       'QUIET', 'ALL')
    with pytest.raises(ValueError):
        fac.causal_regime_session_gate(np.array([100]), np.array([1]), np.array([1.]),
                                       np.array([100]), np.array([1.]),
                                       'UNFROZEN', 'ALL')


@pytest.mark.parametrize('kwargs', [
    {'lookback': 13, 'shock': 2., 'retrace': .4},
    {'lookback': 12, 'shock': 1.75, 'retrace': .4},
    {'lookback': 12, 'shock': 2., 'retrace': .5},
    {'lookback': True, 'shock': 2., 'retrace': .4},
    {'lookback': 12, 'shock': True, 'retrace': .4},
])
def test_nonfrozen_parameters_fail_closed(kwargs):
    with pytest.raises(ValueError):
        fac.shock_reversal_signals(m15_fixture(), **kwargs)


def test_non_utc_or_incomplete_m15_rejected():
    b = m15_fixture()
    naive = b.copy()
    naive.index = naive.index.tz_localize(None)
    with pytest.raises(ValueError):
        fac.shock_reversal_signals(naive, 12, 2., .4)
    broken = b.copy()
    broken.loc[broken.index[20], 'close_at'] = broken.index[20] + pd.Timedelta(minutes=14)
    with pytest.raises(ValueError):
        fac.shock_reversal_signals(broken, 12, 2., .4)


def test_frozen_year_and_limit_gate(tmp_path):
    with pytest.raises(ValueError):
        fac.run_batch(None, 2014, tmp_path/'invalid')
    with pytest.raises(ValueError):
        fac.run_batch(None, 2012, tmp_path/'invalid2', 18433)
    with pytest.raises(ValueError):
        fac.run_batch(None, True, tmp_path/'invalid3')
    with pytest.raises(ValueError):
        fac.run_batch(None, 2012, tmp_path/'invalid4', True)


def test_canonical_signal_costs_are_normalized_without_extra_fee():
    signals = fac.canonical_signals(np.array([1000]), np.array([-1]), np.array([1.5]), 2., 1.)
    assert len(signals) == 1
    assert signals[0].side == -1
    assert signals[0].stop_distance == pytest.approx(3.)
    assert signals[0].target_distance == pytest.approx(1.5)
