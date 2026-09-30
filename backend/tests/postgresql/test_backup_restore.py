"""Restore tests create separate uniquely named databases, never caller tables."""
import importlib
import importlib.util
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@pytest.fixture
def backup_databases():
    raw = os.environ.get('TEST_POSTGRESQL_URL')
    if not raw:
        pytest.skip('Set TEST_POSTGRESQL_URL for real PostgreSQL backup tests')
    url = make_url(raw)
    assert url.get_backend_name() == 'postgresql'
    admin = create_engine(url, isolation_level='AUTOCOMMIT')
    names = [f'ei_backup_{uuid4().hex}' for _ in range(2)]
    created = []
    try:
        with admin.connect() as conn:
            for name in names:
                conn.execute(text(f'CREATE DATABASE "{name}" TEMPLATE template0'))
                created.append(name)
        yield [url.set(database=name).render_as_string(hide_password=False) for name in names]
    finally:
        with admin.connect() as conn:
            for name in created:
                conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def test_postgresql_independent_restore_and_refusals(backup_databases, tmp_path):
    assert importlib.util.find_spec('app.backup'), 'backup component is not implemented'
    module = importlib.import_module('app.backup')
    source, target = backup_databases
    engine = create_engine(source)
    try:
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE parent(id INTEGER PRIMARY KEY)'))
            conn.execute(text('CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))'))
            conn.execute(text('INSERT INTO parent VALUES(1)'))
            conn.execute(text('INSERT INTO child VALUES(1,1)'))
        archive = tmp_path / 'backup.dump'
        manifest = module.backup_database(source, archive)
        assert manifest['tables'] == {'public.parent': 1, 'public.child': 1}
        with pytest.raises(ValueError):
            module.restore_database(archive, source)
        restored = module.restore_database(archive, target)
        assert restored['tables'] == manifest['tables']
        with pytest.raises(ValueError):
            module.restore_database(archive, target)
        target_engine = create_engine(target)
        try:
            with target_engine.connect() as conn:
                assert conn.execute(text('SELECT parent_id FROM child')).all() == [(1,)]
        finally:
            target_engine.dispose()
    finally:
        engine.dispose()


def test_postgresql_manifest_uses_dump_snapshot(backup_databases, tmp_path, monkeypatch):
    from app import backup
    source, target = backup_databases
    engine = create_engine(source)
    try:
        with engine.begin() as conn:
            conn.execute(text('CREATE TABLE event(id INTEGER PRIMARY KEY)'))
            conn.execute(text('INSERT INTO event VALUES(1)'))
        original_run = backup._pg_run

        def write_then_dump(tool, url, args, output=None):
            if tool == 'pg_dump':
                with engine.begin() as conn:
                    conn.execute(text('INSERT INTO event VALUES(2)'))
            return original_run(tool, url, args, output)

        monkeypatch.setattr(backup, '_pg_run', write_then_dump)
        archive = tmp_path / 'snapshot.dump'
        assert backup.backup_database(source, archive)['tables'] == {'public.event': 1}
        assert backup.restore_database(archive, target)['tables'] == {'public.event': 1}
        with engine.connect() as conn:
            assert conn.execute(text('SELECT count(*) FROM event')).scalar_one() == 2
    finally:
        engine.dispose()
