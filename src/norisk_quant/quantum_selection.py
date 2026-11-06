"""Compile supplied training evidence into a bounded binary selection QUBO.

This compiler does not load market data or certify supplied metrics. A claimed
training receipt is carried by identity, never treated as audit acceptance.
Equal-unit candidate utility and covariance are supplied by the coordinator.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re

import numpy as np

from .quantum_optimizer import BinaryProblem


@dataclass(frozen=True)
class SelectionCompilation:
    problem: BinaryProblem
    manifest: dict


def compile_selection(candidates, covariance, select_count, *, risk_aversion=1.0,
                      penalty=None, provenance='synthetic', source_ids=()):
    """Minimize risk_aversion*x'Cov*x - expected_return'x at fixed count.

    Synthetic candidates require id, expected_return and source_id. Supplied
    audited_training candidates additionally require audit_receipt_sha256.
    The receipt's existence/signature is intentionally not asserted here.
    """
    if type(candidates) not in (list, tuple) or not 1 <= len(candidates) <= 16:
        raise ValueError('Require 1..16 supplied candidates')
    if provenance not in {'synthetic', 'audited_training'}:
        raise ValueError('Unknown metric provenance')
    if (type(risk_aversion) not in (int, float)
            or not math.isfinite(risk_aversion) or not 0 <= risk_aversion <= 1e6):
        raise ValueError('Invalid risk aversion')
    required = {'id', 'expected_return', 'source_id'}
    if provenance == 'audited_training':
        required.add('audit_receipt_sha256')
    normalized = []
    for c in candidates:
        if type(c) is not dict or set(c) != required:
            raise ValueError('Candidate fields must match the supplied evidence contract')
        if any(type(c[k]) is not str or not c[k] or len(c[k]) > 128
               for k in ('id', 'source_id')):
            raise ValueError('Candidate and source IDs must be nonempty bounded strings')
        if len(c['id']) > 80:
            raise ValueError('Candidate ID exceeds binary variable label limit')
        utility = c['expected_return']
        if type(utility) not in (int, float) or not math.isfinite(utility) or abs(utility) > 1e6:
            raise ValueError('Invalid candidate utility')
        if provenance == 'audited_training' and (type(c['audit_receipt_sha256']) is not str
                or re.fullmatch('[0-9a-f]{64}', c['audit_receipt_sha256']) is None):
            raise ValueError('Training evidence requires an explicit receipt SHA256')
        normalized.append(dict(c, expected_return=float(utility)))
    if len({c['id'] for c in normalized}) != len(normalized):
        raise ValueError('Duplicate candidate identity')
    if type(source_ids) not in (tuple, list) or any(type(x) is not str for x in source_ids):
        raise ValueError('Invalid supplied source identities')
    observed_sources = sorted({c['source_id'] for c in normalized})
    if source_ids and set(source_ids) != set(observed_sources):
        raise ValueError('Declared source set differs from candidate sources')
    n = len(candidates)
    # Do not coerce bools or strings into numeric research evidence.
    if (type(covariance) not in (tuple, list) or len(covariance) != n
            or any(type(row) not in (tuple, list) or len(row) != n for row in covariance)
            or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e6
                   for row in covariance for x in row)):
        raise ValueError('Require a finite n by n covariance matrix')
    cov = np.asarray(covariance, dtype=float)
    if not np.allclose(cov, cov.T, rtol=0, atol=1e-10):
        raise ValueError('Covariance must be symmetric')
    cov = (cov + cov.T) / 2
    if float(np.linalg.eigvalsh(cov).min()) < -1e-9:
        raise ValueError('Covariance must be positive semidefinite')
    linear = tuple(float(risk_aversion * cov[i, i] - normalized[i]['expected_return'])
                   for i in range(n))
    quadratic = tuple(tuple(float(2 * risk_aversion * cov[i, j]) if i < j else 0.0
                            for j in range(n)) for i in range(n))
    # A unit constraint violation costs more than the maximum possible swing
    # of the unconstrained binary objective. No feasibility claim is inferred
    # from the optimizer's output; the solver reports feasibility separately.
    sufficient = 1.0 + sum(abs(x) for x in linear) + sum(abs(x) for row in quadratic for x in row)
    penalty_value = sufficient if penalty is None else penalty
    problem = BinaryProblem(tuple(c['id'] for c in normalized), linear, quadratic,
                            select_count, penalty_value)
    payload = {
        'schema': 'NRFX_TRAINING_SELECTION_QUBO_V1',
        'metric_provenance': provenance, 'source_ids': observed_sources,
        'candidates': normalized, 'covariance': cov.tolist(),
        'risk_aversion': float(risk_aversion), 'problem': problem.payload(),
        'objective': 'risk_aversion * x.T @ covariance @ x - expected_return.T @ x',
        'supplied_receipts_independently_verified': False,
        'market_data_opened': False, 'trading_approved': False,
    }
    payload['compilation_sha256'] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return SelectionCompilation(problem, payload)
