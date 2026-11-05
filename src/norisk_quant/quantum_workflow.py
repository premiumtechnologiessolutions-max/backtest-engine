"""Explicit local construction workflow; immutable inputs and atomic reports."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time

from .quantum_optimizer import BinaryProblem, solve


def capabilities():
    # Package discovery is not a device compatibility test; do not initialize CUDA.
    return {
        'default_backend': 'numpy_cpu_statevector',
        'optional_packages': {name: importlib.util.find_spec(name) is not None
                              for name in ('pennylane', 'qiskit_aer', 'qibo')},
        'gpu_compatibility': 'NOT_TESTED', 'gpu_execution_implemented': False,
        'market_execution_enabled': False,
    }


def run_problem(source: Path, output: Path, *, layers=1, evaluations=64, seed=0):
    if source.stat().st_size > 1_000_000:
        raise ValueError('Problem JSON exceeds 1 MB')
    raw = source.read_bytes()
    problem = BinaryProblem.from_dict(json.loads(raw))
    started = time.perf_counter()
    result = solve(problem, layers=layers, evaluations=evaluations, seed=seed)
    result['elapsed_seconds'] = time.perf_counter() - started
    result['input_file_sha256'] = hashlib.sha256(raw).hexdigest()
    result['capabilities'] = capabilities()
    result['code_sha256'] = hashlib.sha256(
        Path(__file__).read_bytes() + Path(__file__).with_name('quantum_optimizer.py').read_bytes()
    ).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Immutable reports: refuse overwrite, and publish only a complete JSON file.
    fd, tmp = tempfile.mkstemp(dir=output.parent, prefix='.qaoa-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(tmp, output)
    finally:
        os.unlink(tmp)
    return result


def main():
    parser = argparse.ArgumentParser(description='Local Quantum construction tools; no market jobs')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('capabilities')
    run = sub.add_parser('solve')
    run.add_argument('problem', type=Path)
    run.add_argument('--out', required=True, type=Path)
    run.add_argument('--layers', type=int, default=1)
    run.add_argument('--evaluations', type=int, default=64)
    run.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    if args.command == 'capabilities':
        print(json.dumps(capabilities(), indent=2))
    else:
        result = run_problem(args.problem, args.out, layers=args.layers,
                             evaluations=args.evaluations, seed=args.seed)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
