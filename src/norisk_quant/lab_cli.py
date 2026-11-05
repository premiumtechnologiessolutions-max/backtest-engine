"""Local lab, explicit synthetic workers, and held legacy queue intake."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time

from .lab_coordinator import LabCoordinator
from .lab_server import _reject_constant, _unique_object, create_server

_DEMOS = {
    'synthetic-demo': 'synthetic_campaign',
    'discovery-demo': 'synthetic_discovery',
    'nautilus-demo': 'nautilus_synthetic',
    'lean-demo': 'lean_synthetic',
    'finrl-demo': 'finrl_synthetic',
    'finrl-train-demo': 'finrl_training_synthetic',
    'agent-components-demo': 'synthetic_agent_components',
    'tradingagents-demo': 'tradingagents_graph_synthetic',
    'rdagent-demo': 'rdagent_factor_synthetic',
}


def _read_json(path):
    with path.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('Specification exceeds 64 KB')
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _work(lab, poll_seconds):
    try:
        while True:
            result = lab.run_one()
            if result['state'] == 'IDLE':
                time.sleep(poll_seconds)
            else:
                print(json.dumps({'id': result['id'], 'state': result['state']}), flush=True)
    except KeyboardInterrupt:
        return


def main():
    parser = argparse.ArgumentParser(description='No Risk FX unified construction lab')
    parser.add_argument('--database', type=Path, default=Path.home()/'.noriskfx'/'lab.sqlite3')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--port', type=int, default=8766)
    for name in _DEMOS:
        demo_parser = sub.add_parser(name)
        demo_parser.add_argument('--seed', type=int, default=0)
        if name in {'tradingagents-demo', 'rdagent-demo'}:
            demo_parser.add_argument('--mode', choices=('fixture', 'ollama'), default='fixture')
        if name in {'synthetic-demo', 'discovery-demo'}:
            demo_parser.add_argument('--backend', choices=('numpy', 'pennylane', 'opencl', 'opencl-cpu'),
                                     default='numpy')
            demo_parser.add_argument('--device', help='OpenCL platform and device index, for example 0:0')
    sub.add_parser('status')
    sub.add_parser('work-once')
    worker = sub.add_parser('work', help='Continuously process runnable synthetic jobs')
    worker.add_argument('--poll-seconds', type=float, default=2)
    submit = sub.add_parser('submit')
    submit.add_argument('spec', type=Path)
    proposals = sub.add_parser('import-proposals', help='Queue a typed proposal envelope for synthetic evaluation')
    proposals.add_argument('source', type=Path)
    proposals.add_argument('--seed', type=int, default=0)
    legacy = sub.add_parser('import-legacy', help='Hold historical requests in the unified queue')
    legacy.add_argument('source', type=Path)
    legacy.add_argument('--format', required=True, choices=('frozen-files', 'durable-sqlite'))
    args = parser.parse_args()
    if args.command == 'work' and not .25 <= args.poll_seconds <= 60:
        parser.error('poll-seconds must be between .25 and 60')
    if args.command == 'import-legacy' and args.format == 'durable-sqlite':
        same_path = args.source.resolve() == args.database.resolve()
        same_file = args.source.exists() and args.database.exists() and args.source.samefile(args.database)
        if same_path or same_file:
            parser.error('legacy source and destination must be distinct databases')
    lab = LabCoordinator(args.database)
    if args.command == 'serve':
        server = create_server(lab, port=args.port)
        print(f'No Risk FX local lab: {server.url}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return
    if args.command in _DEMOS:
        kind = _DEMOS[args.command]
        spec = {'kind': kind, 'seed': args.seed}
        if hasattr(args, 'mode'):
            spec['mode'] = args.mode
        if hasattr(args, 'backend'):
            spec['backend'] = args.backend
            if args.device is not None:
                spec['device'] = args.device
        job = lab.submit(spec)
        if job['state'] == 'QUEUED':
            lab.run_one(job_id=job['id'])
        result = lab.job(job['id'])
    elif args.command == 'status':
        result = lab.status()
    elif args.command == 'work-once':
        result = lab.run_one()
    elif args.command == 'work':
        return _work(lab, args.poll_seconds)
    elif args.command == 'import-proposals':
        result = lab.submit({'kind': 'synthetic_external_proposals', 'seed': args.seed,
                             'envelope': _read_json(args.source)})
    elif args.command == 'import-legacy':
        from .lab_legacy import import_legacy_queue
        result = import_legacy_queue(lab.store, args.source, source_format=args.format)
    else:
        result = lab.submit(_read_json(args.spec))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if isinstance(result, dict) and result.get('state') == 'FAILED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
