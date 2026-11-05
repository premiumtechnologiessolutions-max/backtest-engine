"""Import verified frozen request identities into the lab's held inventory."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

from .frozen_queue import _canonical, _verify, list_jobs
from .lab_jobs import JobStore

FORMATS = ('frozen-files', 'durable-sqlite')
MAX_REQUESTS = 10_000
_STATES = {'QUEUED', 'RUNNING', 'RECONCILING', 'CANCEL_REQUESTED', 'CANCELLED', 'QUARANTINED'}
_ACTIVE = {'RUNNING', 'RECONCILING', 'CANCEL_REQUESTED'}
_HEX64 = re.compile(r'[0-9a-f]{64}\Z')
_ATTEMPT_ID = re.compile(r'[0-9a-f]{32}\Z')
_WORKER = re.compile(r'[A-Za-z0-9_.:-]{1,80}\Z')


def _durable_record(row):
    ident = row['request_id']
    raw = row['frozen_json']
    if type(ident) is not str or not _HEX64.fullmatch(ident) or type(raw) is not str or len(raw) > 8192:
        raise ValueError('Invalid durable frozen request metadata')
    request = _verify(json.loads(raw), ident + '.json')
    if _canonical(request).decode('ascii') != raw:
        raise ValueError('Noncanonical durable frozen request bytes')
    state, version, attempt, fence = (row[k] for k in ('state', 'version', 'attempt_no', 'fencing_token'))
    if (type(state) is not str or state not in _STATES
            or any(type(value) is not int or value < 0 for value in (
                version, attempt, fence, row['created_ms'], row['updated_ms']))
            or fence != attempt or version < attempt):
        raise ValueError('Invalid durable source state or attempt metadata')
    attempt_id, worker, lease = (row[k] for k in ('attempt_id', 'worker', 'lease_until_ms'))
    if state in _ACTIVE:
        if (attempt < 1 or type(attempt_id) is not str or not _ATTEMPT_ID.fullmatch(attempt_id)
                or type(worker) is not str or not _WORKER.fullmatch(worker)
                or type(lease) is not int or lease < 0):
            raise ValueError('Invalid active durable source lease')
    elif worker is not None or lease is not None or (state == 'QUEUED' and attempt_id is not None):
        raise ValueError('Inactive durable source retains an active lease or queued attempt')
    snapshot = {
        'source_state': state,
        'source_version': version,
        'source_attempt': attempt,
        'source_fencing_token': fence,
        'source_created_ms': row['created_ms'],
        'source_updated_ms': row['updated_ms'],
    }
    return request, snapshot


def _read_durable(source: Path):
    if source.is_symlink() or source.parent.is_symlink() or not source.is_file():
        raise ValueError('Durable source must be a local regular SQLite file')
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA query_only=ON')
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 65536)
            db.execute('BEGIN')
            tables = db.execute('PRAGMA main.table_list').fetchall()
            if not any(row['name'] == 'jobs' and row['type'] == 'table' for row in tables):
                raise ValueError('Missing durable research jobs table')
            rows = db.execute('''SELECT request_id,frozen_json,state,version,fencing_token,
                attempt_no,attempt_id,worker,lease_until_ms,created_ms,updated_ms
                FROM main.jobs ORDER BY request_id LIMIT ?''', (MAX_REQUESTS + 1,)).fetchall()
            if len(rows) > MAX_REQUESTS:
                raise ValueError(f'Import exceeds {MAX_REQUESTS} historical requests')
            records = [_durable_record(row) for row in rows]
            if len({r[0]['fingerprint'] for r in records}) != len(records):
                raise ValueError('Duplicate request identity in durable research source')
            return records
    except sqlite3.Error as exc:
        raise ValueError('Unable to read the supported durable research SQLite format') from exc


def import_legacy_queue(store: JobStore, source: Path, *, source_format: str) -> dict:
    """Import metadata only from a frozen-file checkout or durable SQLite snapshot.

    Canonical request bytes and identities are verified. Original lifecycle fields
    remain observations of the source. No dataset, attempt result or receipt is read.
    Repeated imports deduplicate by fingerprint and may refresh observed metadata.
    """
    source = Path(source)
    if source_format == 'frozen-files':
        if source.is_symlink() or not source.is_dir():
            raise ValueError('Frozen queue source must be a local checkout directory')
        records = [(request, None) for request in list_jobs(source, limit=MAX_REQUESTS)]
    elif source_format == 'durable-sqlite':
        if source.is_file() and source.samefile(store.path):
            raise ValueError('Historical source and lab database must be distinct')
        records = _read_durable(source)
    else:
        raise ValueError('Unsupported historical research queue format')
    stats = store._stage_legacy(records, source_format)
    return {
        'schema': 'NRFX_LAB_LEGACY_INTAKE_V1',
        'source_format': source_format,
        'requests_seen': len(records),
        'execution_enabled': False,
        **stats,
    }
