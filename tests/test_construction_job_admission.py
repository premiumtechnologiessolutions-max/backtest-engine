import pytest
from scripts.construction_job_admission import admit


def valid():
    return dict(kind='synthetic_unit_test', name='contract_1', source_commit='a'*40,
                fixture='tests/fixtures/synthetic/contract_1.json')


def test_inert():
    result = admit(valid())
    assert result['status'] == 'INERT_APPROVED_SPEC_ONLY'
    assert result['execution_started'] is False
    assert result['market_data_accessed'] is False


@pytest.mark.parametrize('field,value', [
    ('kind', 'backtest'), ('kind', 'openbb_fetch'), ('kind', 'worker'),
    ('kind', 'live_trade'), ('kind', 'synthetic_unit_test; rm -rf /'),
    ('name', '../bad'), ('name', 'bad name'),
    ('source_commit', 'abc'), ('source_commit', 'A'*40),
    ('fixture', '../../Gold data.zip'), ('fixture', 'tests/fixtures/synthetic/../private.json'),
    ('fixture', 'tests/fixtures/synthetic/x.csv'), ('fixture', 'tests/fixtures/synthetic/x.json/other'),
    ('fixture', 'tests/fixtures/synthetic/x.json\n'),
])
def test_reject(field, value):
    spec = valid(); spec[field] = value
    with pytest.raises(ValueError): admit(spec)


def test_reject_extra_fields():
    spec = valid(); spec['command'] = 'python live.py'
    with pytest.raises(ValueError): admit(spec)


def test_reject_bool():
    spec = valid(); spec['name'] = True
    with pytest.raises(ValueError): admit(spec)
