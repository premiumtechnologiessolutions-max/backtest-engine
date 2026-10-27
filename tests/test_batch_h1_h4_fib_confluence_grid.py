"""FAC016 synthetic-only frozen-grid, pivot confirmation, gap and causality gates."""
import numpy as np
import pandas as pd
import pytest

from scripts import batch_h1_h4_fib_confluence_grid as fac


def bars(freq='h', n=50, start='2012-01-02'):
    idx = pd.date_range(start, periods=n, freq=freq, tz='UTC')
    x = np.arange(n)
    center = 100.+4.*np.sin(2*np.pi*x/10)
    width = pd.Timedelta(freq)
    return pd.DataFrame({'h': center+1., 'l': center-1.,
                         'close_at': idx+width}, index=idx)


def m15_fixture(n=40):
    idx = pd.date_range('2012-01-02', periods=n, freq='15min', tz='UTC')
    return pd.DataFrame({'o': np.full(n, 99.5),
                         'h': np.full(n, 100.5),
                         'l': np.full(n, 99.),
                         'c': np.full(n, 100.),
                         'close_at': idx+pd.Timedelta(minutes=15)}, index=idx)


def test_frozen_count_and_fee_and_status():
    assert fac.TOTAL == fac.SPEC['specs_per_year'] == 18000
    assert fac.SPEC['roundtrip_all_in_usd_oz'] == .4
    assert fac.SPEC['years'] == [2012, 2013]


def test_strict_pivot_is_confirmed_only_after_right_bars():
    b = bars()
    ts, sides, lows, highs = fac.confirmed_pivot_waves(b, 2, 3600, 168*3600)
    assert len(ts) > 0 and set(sides.tolist()) == {-1, 1}
    assert np.all(highs > lows)
    # First low pivot near index 7 is only available after index 9 has CLOSED.
    first = int(ts[0])
    assert first >= int(b.close_at.iloc[9].timestamp())
    prefix = b.iloc[:9].copy()
    assert len(fac.confirmed_pivot_waves(prefix, 2, 3600, 168*3600)[0]) == 0
    assert np.array_equal(ts[ts < int(b.close_at.iloc[-1].timestamp())],
                          fac.confirmed_pivot_waves(b, 2, 3600, 168*3600)[0][
                              fac.confirmed_pivot_waves(b, 2, 3600, 168*3600)[0] <
                              int(b.close_at.iloc[-1].timestamp())])


def test_gap_rejects_cross_gap_pivot_and_does_not_fill():
    b = bars(n=11)
    t, _, _, _ = fac.confirmed_pivot_waves(b, 2, 3600, 168*3600)
    missing = b.drop(b.index[7])
    tg, _, _, _ = fac.confirmed_pivot_waves(missing, 2, 3600, 168*3600)
    assert len(tg) <= len(t)
    assert not np.isin(tg, [int(b.close_at.iloc[9].timestamp())]).any()


def test_ambiguous_outside_bar_rejected():
    b = bars(n=15)
    b.loc[b.index[7], 'h'] = 1000.
    b.loc[b.index[7], 'l'] = -1000.
    t, _, _, _ = fac.confirmed_pivot_waves(b, 2, 3600, 168*3600)
    assert int(b.close_at.iloc[9].timestamp()) not in t


def test_nonfrozen_parameters_fail_closed():
    with pytest.raises(ValueError):
        fac.confirmed_pivot_waves(bars(), 4, 3600, 168*3600)
    with pytest.raises(ValueError):
        fac.confluence_signals(m15_fixture(), bars(), bars('4h'), (2, 4), .5, .5)
    with pytest.raises(ValueError):
        fac.confluence_signals(m15_fixture(), bars(), bars('4h'), (2, 2), .618, .5)
    with pytest.raises(ValueError):
        fac.confluence_signals(m15_fixture(), bars(), bars('4h'), (2, 2), .5, 2.)


def test_confluence_only_after_both_pivot_confirmations(monkeypatch):
    m15 = m15_fixture()
    threshold = int(m15.close_at.iloc[25].timestamp())

    def mock_waves(_bars, width, tf_seconds, max_span_seconds):
        return (np.array([threshold], dtype=np.int64),
                np.array([1], dtype=np.int8),
                np.array([95.], dtype=float),
                np.array([105.], dtype=float))

    monkeypatch.setattr(fac, 'confirmed_pivot_waves', mock_waves)
    t, s, base = fac.confluence_signals(m15, bars(), bars('4h'),
                                        (2, 2), .5, .5)
    assert len(t) > 0 and (t >= threshold).all()
    assert (s == 1).all() and (base > 0).all()

    # Future confirmed pivots cannot influence earlier M15 candles.
    def future_waves(_bars, width, tf_seconds, max_span_seconds):
        return (np.array([threshold+999999], dtype=np.int64),
                np.array([1], dtype=np.int8),
                np.array([95.], dtype=float),
                np.array([105.], dtype=float))
    monkeypatch.setattr(fac, 'confirmed_pivot_waves', future_waves)
    assert len(fac.confluence_signals(m15, bars(), bars('4h'),
                                     (2, 2), .5, .5)[0]) == 0


def test_stale_confirmations_and_m15_gap_rejected(monkeypatch):
    m15 = m15_fixture()
    old = int(m15.close_at.iloc[0].timestamp())-337*3600

    def old_waves(_bars, width, tf_seconds, max_span_seconds):
        return (np.array([old], dtype=np.int64),
                np.array([1], dtype=np.int8),
                np.array([95.]), np.array([105.]))
    monkeypatch.setattr(fac, 'confirmed_pivot_waves', old_waves)
    assert len(fac.confluence_signals(m15, bars(), bars('4h'),
                                     (2, 2), .5, 1.5)[0]) == 0

    now = int(m15.close_at.iloc[25].timestamp())
    def fresh_waves(_bars, width, tf_seconds, max_span_seconds):
        return (np.array([now], dtype=np.int64),
                np.array([1], dtype=np.int8),
                np.array([95.]), np.array([105.]))
    monkeypatch.setattr(fac, 'confirmed_pivot_waves', fresh_waves)
    gapped = m15.drop(m15.index[24])
    t, _, _ = fac.confluence_signals(gapped, bars(), bars('4h'),
                                    (2, 2), .5, 1.5)
    assert not np.isin(t, (gapped.close_at.iloc[24:44].astype('int64')//10**9).to_numpy()).any()
