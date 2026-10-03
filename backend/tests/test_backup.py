import importlib
import importlib.util
import json
import sqlite3

import pytest
from sqlalchemy.engine import URL


def api():
    assert importlib.util.find_spec('app.backup'), 'backup component is not implemented'
    return importlib.import_module('app.backup')


def source(tmp_path):
    path = tmp_path / 'source.db'
    with sqlite3.connect(path) as db:
        db.executescript('CREATE TABLE parent(id INTEGER PRIMARY KEY); CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id)); INSERT INTO parent VALUES(1); INSERT INTO child VALUES(1,1);')
    return path


@pytest.mark.parametrize('source_name', ['missing.db', 'backup.db', 'backup.db.manifest.json'])
def test_missing_sqlite_source_cannot_be_created_by_backup(tmp_path, source_name):
    module = api()
    archive = tmp_path / 'backup.db'
    with pytest.raises(ValueError):
        module.backup_database(f'sqlite:///{tmp_path / source_name}', archive)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('url', ['postgresql://user@host/database', 'postgresql:///database'])
def test_pg_connection_requires_explicit_endpoint_before_writing(tmp_path, monkeypatch, url):
    module = api()
    monkeypatch.setenv('PGPORT', '5433')
    monkeypatch.setenv('PGHOST', 'other-server')
    with pytest.raises(ValueError):
        module.backup_database(url, tmp_path / 'refused.dump')
    assert list(tmp_path.iterdir()) == []


def test_pg_inherited_routing_is_refused_for_restore(tmp_path, monkeypatch):
    module = api()
    monkeypatch.setenv('PGHOSTADDR', '192.0.2.1')
    with pytest.raises(ValueError):
        module.restore_database(tmp_path / 'not-opened.dump', 'postgresql://user:password@localhost:5432/target')


@pytest.mark.parametrize('database', ['dbname=other_database', 'postgresql://localhost/other_database', 'postgres://localhost/other_database'])
@pytest.mark.parametrize('operation', ['backup', 'restore'])
def test_pg_connection_string_database_names_are_refused_before_io(tmp_path, database, operation):
    module = api()
    url = URL.create('postgresql', username='user', password='password', host='127.0.0.1', port=1,
                     database=database).render_as_string(hide_password=False)
    archive = tmp_path / 'not-opened.dump'
    with pytest.raises(ValueError, match='literal database name'):
        if operation == 'backup':
            module.backup_database(url, archive)
        else:
            module.restore_database(archive, url)
    assert list(tmp_path.iterdir()) == []


def test_sqlite_roundtrip(tmp_path):
    module = api()
    original = source(tmp_path)
    archive = tmp_path / 'backup.db'
    manifest = module.backup_database(f'sqlite:///{original}', archive)
    assert manifest['tables'] == {'parent': 1, 'child': 1}
    target = tmp_path / 'restored.db'
    result = module.restore_database(archive, f'sqlite:///{target}')
    assert result['tables'] == manifest['tables']
    with sqlite3.connect(target) as db:
        assert db.execute('SELECT parent_id FROM child').fetchall() == [(1,)]


def test_refuses_output_and_existing_target(tmp_path):
    module = api()
    original = source(tmp_path)
    archive = tmp_path / 'backup.db'
    module.backup_database(f'sqlite:///{original}', archive)
    before = original.read_bytes()
    with pytest.raises(ValueError):
        module.backup_database(f'sqlite:///{original}', archive)
    with pytest.raises(ValueError):
        module.restore_database(archive, f'sqlite:///{original}')
    assert original.read_bytes() == before


def test_corruption_and_manifest_count_mismatch(tmp_path):
    module = api()
    original = source(tmp_path)
    archive = tmp_path / 'backup.db'
    module.backup_database(f'sqlite:///{original}', archive)
    target = tmp_path / 'restored.db'
    manifest_path = archive.with_name(archive.name + '.manifest.json')
    manifest = json.loads(manifest_path.read_text())
    manifest['tables']['parent'] = 2
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        module.restore_database(archive, f'sqlite:///{target}')
    assert not target.exists()
    archive.write_bytes(b'corrupt')
    with pytest.raises(ValueError):
        module.restore_database(archive, f'sqlite:///{target}')
    assert not target.exists()


def test_missing_source_is_not_created(tmp_path):
    module = api()
    source_path = tmp_path / 'missing.db'
    with pytest.raises((ValueError, sqlite3.OperationalError)):
        module.backup_database(f'sqlite:///{source_path}', tmp_path / 'backup.db')
    assert not source_path.exists()
