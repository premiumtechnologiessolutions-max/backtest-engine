"""Synthetic regression tests for the FAC017 exported-month audit."""
from pathlib import Path
import pandas as pd
import pytest

from scripts.audit_fac017_local_exports import audit


def fixture(tmp_path: Path):
    base = dict(id='VSE17_N12_Q1.25_R0.25_QUIET_ALL_SL0.50_TP0.50',
                lookback=12, shock=1.25, retrace=.25, regime='QUIET', session='ALL',
                stop_mult=.5, target_mult=.5, signals=110, expired=0, trades=110,
                net_usd_oz=11., fees_usd=44., max_m1_dd=8., positive_months=11,
                worst_month=-1.)
    months = [1.] * 11 + [-1.]
    for i, v in enumerate(months, 1):
        base[f'm{i:02d}'] = v
    annual = pd.DataFrame([base])
    # 11 positive months, $10 net, not $11
    annual.loc[0, 'net_usd_oz'] = 10.
    combined = pd.DataFrame([{
        'id': base['id'], **{f'{k}_{y}': annual.loc[0, k]
                             for y in (2012, 2013)
                             for k in ('trades', 'net_usd_oz', 'max_m1_dd',
                                       'worst_month', 'positive_months', 'fees_usd')},
        'positive_24': 22, 'net_24': 20., 'worst_24': -1.,
        'max_annual_dd': 8., 'fills_both': True, 'gate': True}])
    paths = [tmp_path / f'{x}.csv' for x in ('2012', '2013', 'combined')]
    annual.to_csv(paths[0], index=False)
    annual.to_csv(paths[1], index=False)
    combined.to_csv(paths[2], index=False)
    return paths


def test_valid_fixture(tmp_path):
    p = fixture(tmp_path)
    r = audit(*p, full=False)
    assert r['configs_passing_frozen_joint_gate'] == 1
    assert r['new_backtests_executed_by_this_audit'] == 0


@pytest.mark.parametrize('file_index,column,value', [
    (0, 'm01', 3.), (0, 'fees_usd', 44.01), (1, 'positive_months', 12),
    (0, 'trades', 111), (2, 'positive_24', 24), (2, 'gate', False),
    (0, 'max_m1_dd', -1.), (0, 'id', 'FORGED'), (0, 'm02', float('nan')),
])
def test_corruption_fails_closed(tmp_path, file_index, column, value):
    p = fixture(tmp_path)
    d = pd.read_csv(p[file_index])
    d.loc[0, column] = value
    d.to_csv(p[file_index], index=False)
    with pytest.raises((ValueError, TypeError)):
        audit(*p, full=False)


def test_incomplete_grid_fails_closed(tmp_path):
    p = fixture(tmp_path)
    with pytest.raises(ValueError, match='incomplete frozen grid'):
        audit(*p)
