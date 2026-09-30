import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.config import Settings


BACKEND = Path(__file__).resolve().parents[1]
KEY = 'test-only-signing-material-' + 'a' * 40
PASSWORD = 'test-only-bootstrap-password'


@pytest.fixture
def clean_settings(monkeypatch):
    for field in Settings.model_fields:
        monkeypatch.delenv(field, raising=False)
    monkeypatch.delenv('APP_MODE', raising=False)


def test_default_mode_requires_explicit_secret(clean_settings):
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize('values', [
    {'SECRET_KEY': 'equipment-inspection-secret-key-change-in-production'},
    {'SECRET_KEY': 'change-me-in-production'},
    {'SECRET_KEY': 'short'},
    {'DEBUG': True},
    {'ALGORITHM': 'none'},
    {'SIGNATURE_SECRET': 'short'},
    {'SAFETY_SYSTEM_URL': 'http://safety.local'},
    {'PROCUREMENT_SYSTEM_URL': 'http://procurement.local'},
    {'APP_MODE': 'prodution'},
])
def test_production_rejects_unsafe_settings(clean_settings, values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{'APP_MODE': 'production', 'SECRET_KEY': KEY, **values})


def test_production_valid_configuration_and_demo_opt_in(clean_settings):
    production = Settings(_env_file=None, APP_MODE='production', SECRET_KEY=KEY,
                          SAFETY_SYSTEM_URL='http://safety.local', INTEGRATION_SECRET=KEY,
                          PROCUREMENT_SYSTEM_URL='http://procurement.local',
                          PROCUREMENT_INTEGRATION_TOKEN=KEY)
    assert production.APP_MODE == 'production'
    assert Settings(_env_file=None, APP_MODE='demo').APP_MODE == 'demo'


def isolated_env(tmp_path, mode='production'):
    return {**os.environ, 'PYTHONPATH': str(BACKEND), 'APP_MODE': mode,
            'SECRET_KEY': KEY, 'DATABASE_URL': f'sqlite:///{(tmp_path / "test.db").as_posix()}',
            'UPLOAD_DIR': str(tmp_path / 'uploads'), 'SCHEDULER_ENABLED': 'false',
            'DEBUG': 'false', 'SAFETY_SYSTEM_URL': '', 'PROCUREMENT_SYSTEM_URL': '',
            'STORAGE_BACKEND': 'local'}


def run_python(tmp_path, code, mode='production'):
    return subprocess.run([sys.executable, '-c', code], cwd=tmp_path,
                          env=isolated_env(tmp_path, mode), text=True, encoding='utf-8',
                          capture_output=True, timeout=45)


@pytest.mark.parametrize(('mode', 'expected'), [('production', 0), ('demo', 5)])
def test_lifespan_only_creates_accounts_in_demo(tmp_path, mode, expected):
    run = run_python(tmp_path, '''
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.database import engine
from app.migrate import upgrade_database
from app.models.user import User
upgrade_database(engine)
for _ in range(2):
    with TestClient(app):
        pass
with SessionLocal() as db:
    assert db.query(User).count() == ''' + str(expected), mode)
    assert run.returncode == 0, run.stderr


def test_seed_refuses_production_before_creating_database(tmp_path):
    run = subprocess.run([sys.executable, str(BACKEND / 'seed_data.py')], cwd=tmp_path,
                         env=isolated_env(tmp_path), text=True, encoding='utf-8',
                         capture_output=True, timeout=45)
    assert run.returncode != 0
    assert not (tmp_path / 'test.db').exists()


def test_production_startup_refuses_unmigrated_database(tmp_path):
    run = run_python(tmp_path, '''
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app):
    pass
''')
    assert run.returncode != 0
    assert 'app.migrate upgrade' in run.stderr
    assert not (tmp_path / 'test.db').exists()


def test_bootstrap_cli_refuses_unmigrated_database(tmp_path):
    run = subprocess.run([sys.executable, '-m', 'app.bootstrap_admin', '--username', 'operator',
                          '--password-stdin'], input=PASSWORD + '\n', cwd=tmp_path,
                         env=isolated_env(tmp_path), text=True, encoding='utf-8', capture_output=True, timeout=45)
    assert run.returncode != 0
    assert 'app.migrate upgrade' in run.stderr
    assert not (tmp_path / 'test.db').exists()


def test_demo_seed_still_runs(tmp_path):
    run = subprocess.run([sys.executable, str(BACKEND / 'seed_data.py')], cwd=tmp_path,
                         env=isolated_env(tmp_path, 'demo'), text=True, encoding='utf-8',
                         capture_output=True, timeout=45)
    assert run.returncode == 0, run.stderr
    with sqlite3.connect(tmp_path / 'test.db') as db:
        assert db.execute('select count(*) from users').fetchone()[0] == 5
        assert db.execute('select count(*) from equipments').fetchone()[0] == 18
        assert db.execute('select count(distinct defect_no) from defects').fetchone()[0] == 8


def bootstrap(tmp_path, username='operator', password=PASSWORD):
    migrated = subprocess.run([sys.executable, '-m', 'app.migrate', 'upgrade'], cwd=tmp_path,
                              env=isolated_env(tmp_path), text=True, encoding='utf-8',
                              capture_output=True, timeout=45)
    assert migrated.returncode == 0, migrated.stderr
    return subprocess.run([sys.executable, '-m', 'app.bootstrap_admin', '--username', username,
                           '--password-stdin'], input=password + '\n', cwd=tmp_path,
                          env=isolated_env(tmp_path), text=True, encoding='utf-8',
                          capture_output=True, timeout=45)


def test_bootstrap_is_repeatable_preserves_password_and_audits_once(tmp_path):
    for password in (PASSWORD, 'different-valid-password'):
        run = bootstrap(tmp_path, password=password)
        assert run.returncode == 0, run.stderr
        assert password not in run.stdout + run.stderr
    with sqlite3.connect(tmp_path / 'test.db') as db:
        assert db.execute('select username, role, is_active from users').fetchall() == [('operator', 'ADMIN', 1)]
        assert db.execute('select action from audit_logs').fetchall() == [('user.bootstrap',)]
    run = run_python(tmp_path, '''
from app.database import SessionLocal
from app.models.user import User
from app.api.deps import verify_password
with SessionLocal() as db:
    assert verify_password('test-only-bootstrap-password', db.query(User).one().hashed_password)
''')
    assert run.returncode == 0, run.stderr
    assert bootstrap(tmp_path, username='second-admin').returncode != 0


@pytest.mark.parametrize('password', ['short', 'x' * 73, '密' * 25])
def test_bootstrap_rejects_invalid_password_without_echo(tmp_path, password):
    run = bootstrap(tmp_path, password=password)
    assert run.returncode != 0
    assert password not in run.stdout + run.stderr
    if (tmp_path / 'test.db').exists():
        with sqlite3.connect(tmp_path / 'test.db') as db:
            assert db.execute('select count(*) from users').fetchone()[0] == 0


def test_bootstrap_does_not_promote_existing_non_admin(tmp_path):
    run = run_python(tmp_path, '''
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.database import engine
from app.migrate import upgrade_database
from app.models.user import User, UserRole
from app.api.deps import hash_password
upgrade_database(engine)
with TestClient(app):
    pass
with SessionLocal() as db:
    db.add(User(username='operator', role=UserRole.VIEWER, hashed_password=hash_password('keep-password')))
    db.commit()
''')
    assert run.returncode == 0, run.stderr
    assert bootstrap(tmp_path).returncode != 0
    with sqlite3.connect(tmp_path / 'test.db') as db:
        assert db.execute('select role from users').fetchone()[0] == 'VIEWER'
        assert db.execute('select count(*) from audit_logs').fetchone()[0] == 0


def test_bootstrap_cannot_replace_disabled_administrator(tmp_path):
    assert bootstrap(tmp_path).returncode == 0
    with sqlite3.connect(tmp_path / 'test.db') as db:
        db.execute('update users set is_active = 0')
    run = bootstrap(tmp_path, username='replacement-admin')
    assert run.returncode != 0
    with sqlite3.connect(tmp_path / 'test.db') as db:
        assert db.execute('select username, is_active from users').fetchall() == [('operator', 0)]


def test_concurrent_cli_bootstrap_on_empty_sqlite_database(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(lambda _: bootstrap(tmp_path), range(2)))
    assert all(run.returncode == 0 for run in runs), [run.stderr for run in runs]
    with sqlite3.connect(tmp_path / 'test.db') as db:
        assert db.execute('select count(*) from users').fetchone()[0] == 1
        assert db.execute('select count(*) from audit_logs').fetchone()[0] == 1
