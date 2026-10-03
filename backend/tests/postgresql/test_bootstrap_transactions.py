from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.bootstrap_admin import bootstrap_admin
from app.database import Base
from app.migrate import upgrade_database
from app.models.user import User, UserRole
from app.models.audit import AuditLog


@pytest.mark.parametrize('same_username', [True, False])
@pytest.mark.parametrize('empty_schema', [True, False])
def test_bootstrap_serializes_first_admin_creation(pg_engine, same_username, empty_schema):
    if empty_schema:
        Base.metadata.drop_all(pg_engine)
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE alembic_version'))
        upgrade_database(pg_engine)
    factory = sessionmaker(bind=pg_engine)
    start = Barrier(2)

    def create(username):
        with factory() as db:
            start.wait(timeout=10)
            try:
                return 'created' if bootstrap_admin(db, username, 'test-only-strong-password') else 'unchanged'
            except ValueError:
                db.rollback()
                return 'refused'

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, ['operator-one', 'operator-one' if same_username else 'operator-two']))
    assert sorted(results) == sorted(['created', 'unchanged' if same_username else 'refused'])
    with factory() as db:
        assert db.query(User).one().role == UserRole.ADMIN
        assert db.query(AuditLog).one().action == 'user.bootstrap'


def test_failed_bootstrap_audit_rolls_back_admin(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("ALTER TABLE audit_logs ADD CONSTRAINT test_no_bootstrap CHECK (action <> 'user.bootstrap')"))
    factory = sessionmaker(bind=pg_engine)
    with factory() as db:
        with pytest.raises(IntegrityError):
            bootstrap_admin(db, 'operator', 'test-only-strong-password')
        db.rollback()
        assert db.query(User).count() == 0
        assert db.query(AuditLog).count() == 0
    with pg_engine.begin() as conn:
        conn.execute(text('ALTER TABLE audit_logs DROP CONSTRAINT test_no_bootstrap'))
    with factory() as db:
        assert bootstrap_admin(db, 'operator', 'test-only-strong-password') is True
