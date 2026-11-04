"""Pure construction-only job admission. No execution or file access."""
import re

_ALLOWED = frozenset({'static_audit', 'synthetic_unit_test', 'synthetic_contract_test'})
_SHA = re.compile(r'[0-9a-f]{40}\\Z')
_NAME = re.compile(r'[a-z][a-z0-9_]{0,63}\\Z')
_FIXTURE = re.compile(r'tests/fixtures/synthetic/[A-Za-z0-9_-]+\\.json\\Z')


def admit(spec):
    if type(spec) is not dict or set(spec) != {'kind', 'name', 'source_commit', 'fixture'}:
        raise ValueError('Invalid construction job schema')
    kind, name, commit, fixture = (spec[k] for k in ('kind', 'name', 'source_commit', 'fixture'))
    if type(kind) is not str or kind not in _ALLOWED:
        raise ValueError('Only construction checks are authorized')
    if type(name) is not str or not _NAME.fullmatch(name):
        raise ValueError('Invalid job name')
    if type(commit) is not str or not _SHA.fullmatch(commit):
        raise ValueError('Invalid source commit')
    if type(fixture) is not str or not _FIXTURE.fullmatch(fixture):
        raise ValueError('Only explicit synthetic fixtures are permitted')
    return {'status': 'INERT_APPROVED_SPEC_ONLY', 'kind': kind, 'name': name,
            'source_commit': commit, 'fixture': fixture,
            'execution_started': False, 'market_data_accessed': False}
