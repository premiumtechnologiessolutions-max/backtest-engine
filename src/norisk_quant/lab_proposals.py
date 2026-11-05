"""Typed external formula intake and deterministic synthetic evaluation."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from types import MappingProxyType

from .research_evolution import _formula

SCHEMA = 'NRFX_EXTERNAL_FORMULA_INTAKE_V1'
MAX_PROPOSALS = 128
MAX_LAB_PROPOSALS = 16

# Upstream revisions and licenses verified on GitHub. A caller asserting one
# of these revisions does not prove that upstream generated the formulas.
UPSTREAM_PINS = MappingProxyType({
    'rd-agent': ('microsoft/RD-Agent', '484776c211e4fbbeef03e0ec00d6bbee7362a4f4', 'MIT'),
    'tradingagents': ('TauricResearch/TradingAgents',
                      '9fa1196fffbcfd9de5146d2dd2869df84ab99838', 'Apache-2.0'),
    'openevolve': ('algorithmicsuperintelligence/openevolve',
                   '73448d715968b3578d8458b16295e827edd2b6bf', 'Apache-2.0'),
    'agonalpha': ('AutoResearch-Factory/AgonAlpha',
                  '334f808df72d3da1ff78561d67700a7cf225af15', 'MIT'),
})


def proposal_intake_report(envelope: object, *, max_proposals: int = MAX_PROPOSALS) -> dict:
    """Validate the wire contract and derive unevaluated canonical proposals."""
    if type(max_proposals) is not int or not 1 <= max_proposals <= MAX_PROPOSALS:
        raise ValueError('Invalid external formula intake limit')
    if type(envelope) is not dict or set(envelope) != {
            'schema', 'generator', 'source_commit', 'proposals'}:
        raise ValueError('External proposal contract refuses extra fields or scores')
    generator = envelope['generator']
    if (type(envelope['schema']) is not str or envelope['schema'] != SCHEMA
            or type(generator) is not str or generator not in UPSTREAM_PINS):
        raise ValueError('Unknown source or proposal schema')
    repo, commit, license_id = UPSTREAM_PINS[generator]
    if type(envelope['source_commit']) is not str or envelope['source_commit'] != commit:
        raise ValueError('Source revision not pinned to approved upstream')
    proposals = envelope['proposals']
    if type(proposals) is not list or not 1 <= len(proposals) <= max_proposals:
        raise ValueError(f'External proposal batch must have 1..{max_proposals} formulas')

    canonical = {}
    for row in proposals:
        try:
            formula = _formula(row)
        except OverflowError as exc:
            raise ValueError('Invalid arithmetic formula') from exc
        identity = formula.identity()
        if identity in canonical:
            raise ValueError('Duplicate or equivalent external formula')
        canonical[identity] = asdict(formula)
    return {
        'schema': SCHEMA, 'generator': generator,
        'upstream_repository': repo, 'upstream_commit_asserted': commit,
        'provenance_authenticated': False, 'upstream_license_reported': license_id,
        'formula_count': len(canonical),
        'formulas': [{'identity': identity, 'formula': canonical[identity]}
                     for identity in sorted(canonical)],
        'status': 'PROPOSED_UNEVALUATED', 'independent_oos_proven': False,
        'live_trading_authorized': False, 'execution_performed': False,
    }


def _wire_envelope(report: dict) -> dict:
    return {
        'schema': SCHEMA, 'generator': report['generator'],
        'source_commit': report['upstream_commit_asserted'],
        'proposals': [item['formula'] for item in report['formulas']],
    }


def normalize_proposal_envelope(envelope: object) -> dict:
    """Return a canonical wire envelope for a bounded local lab job."""
    return _wire_envelope(proposal_intake_report(envelope, max_proposals=MAX_LAB_PROPOSALS))


def run_proposal_campaign(spec: dict, progress=lambda stage: None) -> dict:
    """Evaluate submitted parameters; the lab never invokes the asserted generator."""
    # The coordinator routes jobs here and also supplies the canonical fixtures
    # and parity check. Keep this import local so routing can import this module.
    from .execution import run
    from .fast_engine import run_fast
    from .lab_coordinator import _bounded, _frame_digest, _parity, synthetic_fixture
    from .math_discovery import Formula, arithmetic_signals
    from .model import Settings

    if type(spec) is not dict or set(spec) - {
            'kind', 'envelope', 'bars', 'seed', 'code_sha256', 'runtime'}:
        raise ValueError('External proposal jobs accept only an envelope and synthetic fixture controls')
    report = proposal_intake_report(spec.get('envelope'), max_proposals=MAX_LAB_PROPOSALS)
    bars = _bounded(spec.get('bars', 360), 'bars', 240, 1440)
    seed = _bounded(spec.get('seed', 0), 'seed', 0, 2**32 - 1)
    wire = json.dumps(_wire_envelope(report), sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')
    stages = ['external_proposal_fixture']
    progress(stages[0])
    minutes = synthetic_fixture(bars, seed)
    settings = Settings(ounces=1., roundtrip_cost_per_ounce=.4, max_holding_minutes=60)
    candidates = []
    for index, item in enumerate(report['formulas'], start=1):
        stage = f'external_proposal_{index}'
        progress(stage)
        stages.append(stage)
        formula = Formula(**item['formula'])
        signals = arithmetic_signals(minutes, formula)
        reference = run(minutes, signals, settings)
        fast = run_fast(minutes, signals, settings)
        _parity(reference, fast)
        equity = reference.equity['equity']
        peak = equity.cummax().clip(lower=0)
        stride = max(1, (len(equity) + 78) // 79)
        curve = [float(x) for x in equity.iloc[:-1:stride]] + [float(equity.iloc[-1])]
        candidates.append({
            'id': item['identity'], 'parameters': item['formula'],
            'expression': formula.expression(), 'signals': len(signals),
            'trades': len(reference.trades), 'net_usd_per_oz': float(equity.iloc[-1]),
            'max_drawdown_usd_per_oz': float((peak - equity).clip(lower=0).max()),
            'parity_passed': True, 'trade_ledger_sha256': _frame_digest(reference.trades),
            'equity_sha256': _frame_digest(reference.equity), 'curve': curve,
        })
    return {
        'schema': 'NRFX_SYNTHETIC_EXTERNAL_PROPOSALS_V1', 'intake_schema': SCHEMA,
        'status': 'EVALUATED_SYNTHETIC_ONLY', 'provenance': 'SYNTHETIC_NOT_MARKET',
        'generator': report['generator'], 'upstream_repository': report['upstream_repository'],
        'upstream_commit_asserted': report['upstream_commit_asserted'],
        'upstream_license_reported': report['upstream_license_reported'],
        'provenance_authenticated': False, 'upstream_runtime_executed': False,
        'envelope_sha256': hashlib.sha256(wire).hexdigest(),
        'fixture_sha256': _frame_digest(minutes), 'bars': bars, 'seed': seed,
        'cost_per_ounce': settings.roundtrip_cost_per_ounce, 'formula_count': len(candidates),
        'market_data_accessed': False, 'live_trading_enabled': False,
        'independent_oos_proven': False, 'candidates': candidates, 'stages': [*stages, 'complete'],
        'limitations': ['The asserted upstream did not run in the lab; formula authorship is unverified',
                        'Results come only from invented OHLC and independent synthetic accounts',
                        'Execution parity does not establish a market edge or out-of-sample evidence'],
    }
