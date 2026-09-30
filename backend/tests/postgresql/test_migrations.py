import pytest
from sqlalchemy import text

from app.database import Base
from tests.test_migrations import MigrationChecks


class TestPostgresMigrations(MigrationChecks):
    @pytest.mark.parametrize('versioned', [True, False])
    def test_wrong_serial_reference_is_refused(self, migration_engine, versioned):
        from app.migrate import upgrade_database, check_database
        if versioned:
            upgrade_database(migration_engine)
        else:
            Base.metadata.create_all(migration_engine)
        with migration_engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ALTER COLUMN id SET DEFAULT nextval('equipments_id_seq')"))
        with pytest.raises(RuntimeError, match='structure'):
            (check_database if versioned else upgrade_database)(migration_engine)

    @pytest.fixture
    def migration_engine(self, pg_engine):
        Base.metadata.drop_all(pg_engine)
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS alembic_version'))
        return pg_engine
