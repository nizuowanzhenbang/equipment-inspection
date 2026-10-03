import pytest
from sqlalchemy import create_engine, inspect, text

from app.database import Base
from app.main import app  # register the current ORM, independently of frozen migration DDL


class MigrationChecks:
    def test_failed_ddl_rolls_back_known_additions_and_version(self, migration_engine):
        from app.migrate import upgrade_database
        from sqlalchemy import event
        from sqlalchemy.exc import DBAPIError
        engine = migration_engine
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE work_tickets DROP COLUMN signatures'))
            conn.execute(text('ALTER TABLE operation_tickets DROP COLUMN signatures'))
            conn.execute(text('DROP INDEX uq_inspection_record_task_point'))

        def fail_at_index(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith('CREATE UNIQUE INDEX uq_inspection_record_task_point'):
                conn.exec_driver_sql('SELECT * FROM intentional_missing_migration_table')

        event.listen(engine, 'before_cursor_execute', fail_at_index)
        try:
            with pytest.raises(DBAPIError):
                upgrade_database(engine)
        finally:
            event.remove(engine, 'before_cursor_execute', fail_at_index)
        assert 'alembic_version' not in inspect(engine).get_table_names()
        assert 'signatures' not in {c['name'] for c in inspect(engine).get_columns('work_tickets')}
        upgrade_database(engine)

    def test_empty_database_upgrade_and_repeat_preserve_data(self, migration_engine):
        from app.migrate import upgrade_database, check_database
        engine = migration_engine
        upgrade_database(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (username, hashed_password, role, is_active) "
                                    "VALUES ('sentinel', 'unchanged', 'ADMIN', true)"))
        upgrade_database(engine)
        check_database(engine)
        with engine.connect() as connection:
            assert connection.scalar(text('select count(*) from users')) == 1
            assert connection.scalar(text('select hashed_password from users')) == 'unchanged'

    @pytest.mark.parametrize('legacy', ['current', 'bootstrap', 'missing_additions'])
    def test_known_unversioned_schemas_are_adopted(self, migration_engine, legacy):
        from app.migrate import upgrade_database, check_database
        from app.models.user import User
        from app.models.audit import AuditLog
        engine = migration_engine
        tables = [User.__table__, AuditLog.__table__] if legacy == 'bootstrap' else None
        Base.metadata.create_all(engine, tables=tables)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (username, hashed_password, role, is_active) "
                              "VALUES ('legacy', 'untouched', 'VIEWER', true)"))
            if legacy == 'missing_additions':
                conn.execute(text('ALTER TABLE work_tickets DROP COLUMN signatures'))
                conn.execute(text('ALTER TABLE operation_tickets DROP COLUMN signatures'))
                conn.execute(text('DROP INDEX uq_inspection_record_task_point'))
        upgrade_database(engine)
        check_database(engine)
        with engine.connect() as conn:
            assert conn.scalar(text('select hashed_password from users')) == 'untouched'
        assert 'signatures' in {c['name'] for c in inspect(engine).get_columns('work_tickets')}

    def test_unknown_structure_refused_without_version_or_column_mutation(self, migration_engine):
        from app.migrate import upgrade_database
        engine = migration_engine
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE users ADD COLUMN unknown_column INTEGER'))
            conn.execute(text('ALTER TABLE work_tickets DROP COLUMN signatures'))
        with pytest.raises(RuntimeError, match='structure|结构'):
            upgrade_database(engine)
        assert 'alembic_version' not in inspect(engine).get_table_names()
        assert 'signatures' not in {c['name'] for c in inspect(engine).get_columns('work_tickets')}

    def test_same_index_name_with_wrong_columns_is_refused(self, migration_engine):
        from app.migrate import upgrade_database
        engine = migration_engine
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text('DROP INDEX uq_inspection_record_task_point'))
            conn.execute(text('CREATE UNIQUE INDEX uq_inspection_record_task_point ON inspection_records(task_id)'))
        with pytest.raises(RuntimeError, match='structure|结构'):
            upgrade_database(engine)
        assert 'alembic_version' not in inspect(engine).get_table_names()

    def test_current_revision_does_not_hide_drift(self, migration_engine):
        from app.migrate import upgrade_database, check_database
        engine = migration_engine
        upgrade_database(engine)
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE users ADD COLUMN drift INTEGER'))
        with pytest.raises(RuntimeError, match='structure|结构'):
            check_database(engine)

    def test_unknown_revision_is_not_overwritten(self, migration_engine):
        from app.migrate import upgrade_database
        engine = migration_engine
        upgrade_database(engine)
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num='future_revision'"))
        with pytest.raises(RuntimeError, match='version|版本'):
            upgrade_database(engine)
        with engine.connect() as conn:
            assert conn.scalar(text('select version_num from alembic_version')) == 'future_revision'

    def test_duplicate_records_preserved_when_legacy_upgrade_refused(self, migration_engine):
        from app.migrate import upgrade_database
        from app.models.equipment import Equipment, EquipmentSystem
        from app.models.route import InspectionRoute, InspectionPoint
        from app.models.task import InspectionTask, InspectionRecord
        from sqlalchemy.orm import Session
        from datetime import datetime
        engine = migration_engine
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text('DROP INDEX uq_inspection_record_task_point'))
        with Session(engine) as db:
            equipment = Equipment(code='LEGACY', name='keep', equipment_system=EquipmentSystem.BOILER)
            route = InspectionRoute(route_no='LEGACY', name='keep')
            db.add_all([equipment, route])
            db.flush()
            point = InspectionPoint(point_no='LEGACY', route_id=route.id, equipment_id=equipment.id, check_items=[])
            task = InspectionTask(task_no='LEGACY', route_id=route.id, scheduled_at=datetime.utcnow())
            db.add_all([point, task])
            db.flush()
            db.add_all([InspectionRecord(task_id=task.id, point_id=point.id) for _ in range(2)])
            db.commit()
        with pytest.raises(RuntimeError, match='[Dd]uplicate|重复'):
            upgrade_database(engine)
        with engine.connect() as conn:
            assert conn.scalar(text('select count(*) from inspection_records')) == 2
        assert 'alembic_version' not in inspect(engine).get_table_names()


class TestSQLiteMigrations(MigrationChecks):
    @pytest.mark.parametrize('versioned', [True, False])
    def test_sqlite_collation_drift_is_refused(self, migration_engine, versioned):
        from app.migrate import upgrade_database, check_database
        if versioned:
            upgrade_database(migration_engine)
        else:
            Base.metadata.create_all(migration_engine)
        with migration_engine.begin() as conn:
            conn.execute(text('DROP INDEX ix_users_username'))
            conn.execute(text('CREATE UNIQUE INDEX ix_users_username ON users(username COLLATE NOCASE)'))
        with pytest.raises(RuntimeError, match='structure'):
            (check_database if versioned else upgrade_database)(migration_engine)

    def test_sqlite_unreflected_expression_index_is_refused(self, migration_engine):
        from app.migrate import upgrade_database
        Base.metadata.create_all(migration_engine)
        with migration_engine.begin() as conn:
            conn.execute(text('CREATE UNIQUE INDEX unexpected_casefold ON users(lower(username))'))
        with pytest.raises(RuntimeError, match='structure'):
            upgrade_database(migration_engine)
        assert 'alembic_version' not in inspect(migration_engine).get_table_names()

    @pytest.fixture
    def migration_engine(self, tmp_path):
        engine = create_engine(f'sqlite:///{(tmp_path / "migration.db").as_posix()}')
        yield engine
        engine.dispose()
