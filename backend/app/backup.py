"""Standalone, non-overwriting database backups and isolated restores."""
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError


def _manifest_path(path):
    return path.with_name(path.name + '.manifest.json')


def _sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _sqlite_path(url):
    parsed = make_url(url)
    if parsed.query or not parsed.database or parsed.database == ':memory:':
        raise ValueError('Use a plain file SQLite URL')
    return Path(parsed.database).resolve()


def _validate_pg_url(url):
    parsed = make_url(url)
    if not all((parsed.host, parsed.port, parsed.username, parsed.database)):
        raise ValueError('PostgreSQL URL must explicitly include host, port, user and database')
    if any(key.startswith('PG') and key not in {'PG_DUMP', 'PG_RESTORE'} for key in os.environ):
        raise ValueError('Use explicit PostgreSQL URL settings; inherited PG connection defaults are not supported')
    allowed = {'sslmode', 'sslcert', 'sslkey', 'sslrootcert', 'connect_timeout'}
    if set(parsed.query) - allowed:
        raise ValueError('Unsupported PostgreSQL connection options')
    return parsed


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _sqlite_counts(db):
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
    return {name: db.execute(f'SELECT count(*) FROM {_quote(name)}').fetchone()[0] for (name,) in tables}


def _sqlite_validate(db):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('SQLite integrity check failed')
    if db.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Foreign key validation failed')


def _pg_counts(conn):
    tables = conn.execute(text("SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema') AND schemaname NOT LIKE 'pg_toast%'")).all()
    return {f'{schema}.{name}': conn.execute(text(f'SELECT count(*) FROM {_quote(schema)}.{_quote(name)}')).scalar_one() for schema, name in tables}


def _pg_identity(conn):
    # Database OID plus server endpoint identifies the source without storing credentials.
    return list(conn.execute(text("SELECT current_database(), (SELECT oid::text FROM pg_database WHERE datname=current_database()), coalesce(inet_server_addr()::text, 'local'), inet_server_port()")).one())


def _pg_empty(conn):
    return not conn.execute(text("""
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'
        UNION ALL SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema')
        UNION ALL SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname NOT IN ('pg_catalog','information_schema')
        UNION ALL SELECT 1 FROM pg_namespace WHERE nspname NOT IN ('public','pg_catalog','information_schema') AND nspname NOT LIKE 'pg_%'
        UNION ALL SELECT 1 FROM pg_extension WHERE extname <> 'plpgsql'
        LIMIT 1
    """)).first()


def _pg_validate(conn):
    # pg_restore creates FK constraints after loading data; require each validated.
    if conn.execute(text("SELECT 1 FROM pg_constraint WHERE contype='f' AND NOT convalidated LIMIT 1")).first():
        raise ValueError('Unvalidated foreign key constraint')


def _pg_run(tool, url, args, output=None):
    parsed = _validate_pg_url(url)
    allowed = {'sslmode', 'sslcert', 'sslkey', 'sslrootcert', 'connect_timeout'}
    if set(parsed.query) - allowed:
        raise ValueError('Unsupported PostgreSQL connection options')
    env = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
    env.update(PGHOST=parsed.host or '', PGPORT=str(parsed.port or 5432),
               PGDATABASE=parsed.database or '', PGUSER=parsed.username or '',
               PGPASSWORD=parsed.password or '', PGCONNECT_TIMEOUT='10')
    for key, value in parsed.query.items():
        env['PG' + key.upper()] = value
    executable = os.environ.get(tool.upper(), tool)
    try:
        result = subprocess.run([executable, *args], env=env, stdout=output or subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False)
    except OSError:
        raise ValueError(f'{tool} could not be started; configure its executable path') from None
    if result.returncode:
        # Server errors may echo secrets in arbitrary SQL, so never relay stderr.
        raise ValueError(f'{tool} failed (exit {result.returncode}); target may need inspection')


def backup_database(url: str, output: Path) -> dict:
    output = Path(output).absolute()
    manifest_path = _manifest_path(output)
    if output.exists() or manifest_path.exists():
        raise ValueError('Backup or manifest already exists')
    backend = make_url(url).get_backend_name()
    if backend not in {'sqlite', 'postgresql'}:
        raise ValueError('Unsupported database backend')
    if backend == 'sqlite':
        source = _sqlite_path(url)
        if not source.is_file() or source in {output.resolve(), manifest_path.resolve()}:
            raise ValueError('SQLite source must be an existing independent file')
    else:
        _validate_pg_url(url)
    claimed = []
    try:
        # Exclusive creation prevents concurrent backup writers from overwriting.
        with output.open('xb') as archive:
            claimed.append(output)
            with manifest_path.open('x', encoding='utf-8') as manifest_file:
                claimed.append(manifest_path)
                if backend == 'sqlite':
                    source = _sqlite_path(url)
                    with (closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src,
                          closing(sqlite3.connect(output)) as dest):
                        src.backup(dest)
                        _sqlite_validate(dest)
                        counts = _sqlite_counts(dest)
                    identity = str(source)
                else:
                    engine = create_engine(url, isolation_level='REPEATABLE READ')
                    try:
                        with engine.begin() as conn:
                            conn.execute(text('SET TRANSACTION READ ONLY'))
                            snapshot = conn.execute(text('SELECT pg_export_snapshot()')).scalar_one()
                            identity = _pg_identity(conn)
                            counts = _pg_counts(conn)
                            _pg_validate(conn)
                            _pg_run('pg_dump', url, ['--format=custom', '--no-owner', '--no-privileges',
                                                    '--snapshot=' + snapshot], archive)
                    finally:
                        engine.dispose()
                archive.flush()
                manifest = {'version': 1, 'backend': backend, 'sha256': _sha256(output),
                            'created_at': datetime.now(timezone.utc).isoformat(),
                            'source': identity, 'tables': counts}
                json.dump(manifest, manifest_file, indent=2, ensure_ascii=False)
        return manifest
    except FileExistsError:
        for path in reversed(claimed):
            path.unlink(missing_ok=True)
        raise ValueError('Backup or manifest already exists') from None
    except BaseException:
        for path in reversed(claimed):
            path.unlink(missing_ok=True)
        raise


def restore_database(archive: Path, target_url: str) -> dict:
    archive = Path(archive).absolute()
    backend = make_url(target_url).get_backend_name()
    if backend == 'postgresql':
        _validate_pg_url(target_url)
    manifest = json.loads(_manifest_path(archive).read_text(encoding='utf-8'))
    if manifest.get('version') != 1 or manifest.get('backend') != backend:
        raise ValueError('Unsupported manifest or database backend mismatch')
    if _sha256(archive) != manifest.get('sha256'):
        raise ValueError('Backup SHA256 mismatch')
    if backend == 'sqlite':
        target = _sqlite_path(target_url)
        if target.exists() or str(target) == manifest.get('source'):
            raise ValueError('Restore requires a new independent SQLite file')
        # Validate first: a corrupt manifest must not produce a target.
        with closing(sqlite3.connect(archive.as_uri() + '?mode=ro', uri=True)) as src:
            _sqlite_validate(src)
            if _sqlite_counts(src) != manifest['tables']:
                raise ValueError('Backup table counts mismatch')
            try:
                with target.open('xb'):
                    pass
            except FileExistsError:
                raise ValueError('Restore target already exists') from None
            try:
                with closing(sqlite3.connect(target)) as dest:
                    src.backup(dest)
                    _sqlite_validate(dest)
                    if _sqlite_counts(dest) != manifest['tables']:
                        raise ValueError('Restored table counts mismatch')
            except BaseException:
                target.unlink(missing_ok=True)
                raise
    elif backend == 'postgresql':
        engine = create_engine(target_url)
        try:
            with engine.connect() as conn:
                if _pg_identity(conn) == manifest.get('source') or not _pg_empty(conn):
                    raise ValueError('Restore requires an independent empty PostgreSQL database')
            _pg_run('pg_restore', target_url, ['--dbname=' + make_url(target_url).database,
                    '--single-transaction', '--exit-on-error', '--no-owner', '--no-privileges', str(archive)])
            with engine.connect() as conn:
                _pg_validate(conn)
                if _pg_counts(conn) != manifest['tables']:
                    raise ValueError('Restored table counts mismatch; isolate target for inspection')
        finally:
            engine.dispose()
    else:
        raise ValueError('Unsupported database backend')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'restore'])
    parser.add_argument('archive', type=Path)
    parser.add_argument('--url-env', required=True, help='Environment variable containing source/target URL')
    args = parser.parse_args()
    url = os.environ.get(args.url_env)
    if not url:
        parser.error('The named URL environment variable is empty')
    try:
        result = (backup_database(url, args.archive) if args.action == 'backup'
                  else restore_database(args.archive, url))
    except (ValueError, OSError, sqlite3.Error, SQLAlchemyError, KeyError, TypeError):
        # SQLAlchemy/driver exceptions may contain connection credentials.
        parser.exit(1, 'Database operation failed; check connectivity, integrity, and independent empty target.\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
