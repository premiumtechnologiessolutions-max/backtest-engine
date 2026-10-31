"""Synthetic-only tests: no original quotes, no fills, no P/L."""
import pytest
from datetime import datetime, timezone
from scripts.research_fac025_source_feasibility import inspect_year

BASE = 1325462400  # 2012-01-02 00:00:00 UTC


def fixture_rows():
    rows=[]
    for i in range(5*60+3):
        t=BASE+i*60
        o,h,l,c=100.1,100.2,100.0,100.1
        if i==3*60-1:
            c=100.1
        if i==4*60-1:
            c=100.15
        if 4*60+45<=i<5*60:
            l=99.95
            if i==5*60-1:
                c=100.05
        rows.append(dict(ts=t,o=o,h=h,l=l,c=c,ao=o+.02,ah=h+.02,al=l+.02,ac=c+.02))
    return rows


def test_sweep_with_two_older_h1_and_next_open_observed():
    r=inspect_year(fixture_rows())
    assert r['counts']['normalized_risk_passed_intents']==1
    assert r['counts']['next_minute_open_observed_not_fill']==1
    assert r['months']['2012-01']=={'candidates':1,'next_open_observed':1}


def test_missing_next_open_does_not_invent_fill():
    rows=[x for x in fixture_rows() if x['ts'] != BASE+(5*60+2)*60]
    r=inspect_year(rows)
    assert r['counts']['normalized_risk_passed_intents']==1
    assert r['counts'].get('next_minute_open_observed_not_fill',0)==0


def test_missing_prior_h1_minute_blocks_candidate():
    rows=[x for x in fixture_rows() if x['ts'] != BASE+3*60*60+5*60]
    r=inspect_year(rows)
    assert r['counts'].get('normalized_risk_passed_intents',0)==0


@pytest.mark.parametrize('mutate',[
    lambda x:x.__setitem__('ts',x['ts']+1),
    lambda x:x.__setitem__('al',x['l']-.1),
    lambda x:x.__setitem__('o',True),
    lambda x:x.__setitem__('h',x['l']-.1),
])
def test_invalid_source_fails_closed(mutate):
    rows=fixture_rows();mutate(rows[10])
    with pytest.raises(ValueError):inspect_year(rows)


def test_unsorted_duplicate_fails_closed():
    rows=fixture_rows();rows[20]['ts']=rows[19]['ts']
    with pytest.raises(ValueError):inspect_year(rows)


@pytest.mark.parametrize("shift_hours,session_08_12,session_09_13", [
    (8, 1, 0),   # January NY 08:01: first frozen session only.
    (9, 1, 1),   # January NY 09:01: overlap of both frozen sessions.
    (12, 0, 1),  # January NY 12:01: second session only.
])
def test_frozen_ny_session_boundaries_on_observed_later_open(
        shift_hours, session_08_12, session_09_13):
    rows = fixture_rows()
    for row in rows:
        row['ts'] += shift_hours * 3600
    counts = inspect_year(rows)['counts']
    assert counts.get('ny_08_12_observed_open_candidates', 0) == session_08_12
    assert counts.get('ny_09_13_observed_open_candidates', 0) == session_09_13
    assert counts['normalized_risk_passed_intents'] == 1


def test_frozen_ny_session_uses_summer_dst_not_fixed_utc_offset():
    rows = fixture_rows()
    summer_start = int(datetime(2012, 7, 2, 7, tzinfo=timezone.utc).timestamp())
    for row in rows:
        row['ts'] += summer_start - BASE
    counts = inspect_year(rows)['counts']
    # July 12:01 UTC is New York 08:01 EDT, not 07:01 EST.
    assert counts['ny_08_12_observed_open_candidates'] == 1
    assert counts.get('ny_09_13_observed_open_candidates', 0) == 0


def test_missing_later_open_never_counted_in_frozen_ny_session():
    rows = fixture_rows()
    for row in rows:
        row['ts'] += 9 * 3600
    missing = BASE + 9 * 3600 + (5 * 60 + 2) * 60
    result = inspect_year([row for row in rows if row['ts'] != missing])
    assert result['counts']['normalized_risk_passed_intents'] == 1
    assert result['counts'].get('ny_08_12_observed_open_candidates', 0) == 0
    assert result['counts'].get('ny_09_13_observed_open_candidates', 0) == 0
