"""Exact joint YEAR-BLOCK sign-flip search-multiplicity diagnostic.

Research-only sensitivity analysis. Assumes the *entire multivariate annual
strategy-return vector* is sign-symmetric under a joint null, an assumption
NOT established by historical gold data. This is not an OOS proof or a
promotion gate. Shared flips preserve candidate dependence under the null.
"""
from __future__ import annotations

import math
import re

import numpy as np

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def exact_joint_signflip(annual_pnl: dict[str, list[float]], *,
                         min_years: int = 2, max_years: int = 16,
                         chunk_size: int = 256) -> dict:
    """Return single-step maxT adjusted exact fractions from the full universe.

    Self-normalized one-sided test T=sum(annual_PnL)/sqrt(sum(annual_PnL**2)).
    Year blocks are flipped TOGETHER for every strategy; this preserves
    within-year cross-strategy correlation in the hypothetical null sample.
    Includes all 2**Y sign vectors, including the observed all-positive one.

    Do not interpret as a p-value valid without sign-symmetry, independent
    year-block exchangeability, and a fully frozen unsearched candidate set.
    """
    if (type(annual_pnl) is not dict or not annual_pnl
            or type(min_years) is not int or min_years < 2
            or type(max_years) is not int or max_years < min_years or max_years > 16
            or type(chunk_size) is not int or not 1 <= chunk_size <= 4096):
        raise ValueError("Invalid frozen sign-flip matrix or controls")
    ids = sorted(annual_pnl)
    if any(type(i) is not str or not i or not _HEX64.fullmatch(i) for i in ids):
        raise ValueError("Candidates require canonical immutable SHA256 identities")
    values = [annual_pnl[i] for i in ids]
    if any(type(v) is not list for v in values):
        raise ValueError("Annual returns must be explicit lists")
    n_years = len(values[0])
    if n_years < min_years or n_years > max_years or any(len(v) != n_years for v in values):
        raise ValueError("All candidates require equal complete annual periods")
    if any(type(x) not in (int, float) or not math.isfinite(x)
           for series in values for x in series):
        raise ValueError("Annual P/L must be finite numeric, never bool or text")
    matrix = np.array(values, dtype=np.float64)
    norms = np.sqrt(np.sum(matrix * matrix, axis=1))
    if not np.isfinite(norms).all():
        raise ValueError("Unbounded annual return magnitude")
    normed = np.divide(matrix, norms[:, None],
                       out=np.zeros_like(matrix), where=norms[:, None] > 0)
    observed = normed.sum(axis=1)
    count_raw = np.zeros(len(ids), dtype=np.int64)
    count_max = np.zeros(len(ids), dtype=np.int64)
    all_patterns = 1 << n_years
    mask = np.arange(n_years, dtype=np.int64)
    for start in range(0, all_patterns, chunk_size):
        end = min(start + chunk_size, all_patterns)
        codes = np.arange(start, end, dtype=np.int64)
        signs = np.where((codes[:, None] >> mask) & 1, 1., -1.)
        null_stats = signs @ normed.T
        count_raw += np.sum(null_stats >= observed[None, :] - 1e-12, axis=0)
        max_null_stats = np.maximum(0., null_stats.max(axis=1))
        count_max += np.sum(max_null_stats[:, None] >= observed[None, :] - 1e-12,
                            axis=0)
    results = {}
    for j, identity in enumerate(ids):
        results[identity] = {
            "observed_self_normalized_annual_t": round(float(observed[j]), 9),
            "one_sided_unadjusted_exact_fraction": [int(count_raw[j]), all_patterns],
            "maxT_family_adjusted_exact_fraction": [int(count_max[j]), all_patterns],
            "one_sided_unadjusted_p": round(float(count_raw[j]) / all_patterns, 9),
            "maxT_family_adjusted_p": round(float(count_max[j]) / all_patterns, 9),
        }
    return {
        "method": "EXACT_SHARED_YEAR_BLOCK_SIGNFLIP_MAXT_DIAGNOSTIC_ONLY",
        "candidate_count": len(ids),
        "training_year_blocks": n_years,
        "enumerated_joint_patterns": all_patterns,
        "null_assumption_unverified": (
            "Joint sign symmetry of annual candidate-return vectors; "
            "cross-year dependence and strategy search can violate it."
        ),
        "independent_oos_proven": False,
        "selection_or_live_authority": "NONE",
        "results": results,
    }
