"""Unified local lab entry point; no market jobs or autonomous daemon starts."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from .lab_coordinator import LabCoordinator
from .lab_server import create_server


def main():
    parser = argparse.ArgumentParser(description='No Risk FX unified construction lab')
    parser.add_argument('--database', type=Path, default=Path.home()/'.noriskfx'/'lab.sqlite3')
    sub = parser.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--port', type=int, default=8766)
    demo = sub.add_parser('synthetic-demo')
    demo.add_argument('--seed', type=int, default=0)
    for name in ('discovery-demo','nautilus-demo'):
        demo_parser = sub.add_parser(name)
        demo_parser.add_argument('--seed',type=int,default=0)
    sub.add_parser('status')
    sub.add_parser('work-once')
    submit = sub.add_parser('submit')
    submit.add_argument('spec', type=Path)
    args = parser.parse_args()
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
    if args.command in {'synthetic-demo','discovery-demo','nautilus-demo'}:
        kind = {'synthetic-demo':'synthetic_campaign','discovery-demo':'synthetic_discovery',
                'nautilus-demo':'nautilus_synthetic'}[args.command]
        job = lab.submit({'kind':kind, 'seed':args.seed})
        # Do not unexpectedly execute an unrelated older queued job.
        if job['state'] == 'QUEUED':
            oldest = next((j for j in reversed(lab.list_jobs()) if j['state']=='QUEUED'), None)
            if oldest and oldest['id'] == job['id']:
                lab.run_one()
        result = lab.job(job['id'])
    elif args.command == 'status':
        result = lab.status()
    elif args.command == 'work-once':
        result = lab.run_one()
    else:
        if args.spec.stat().st_size > 65536:
            raise ValueError('Specification exceeds 64 KB')
        result = lab.submit(json.loads(args.spec.read_text(encoding='utf-8')))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if isinstance(result, dict) and result.get('state') == 'FAILED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
