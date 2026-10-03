"""Real PostgreSQL tests own a random schema; application databases are untouched."""
import os
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.api.deps import create_access_token, get_db
from app.config import settings
from app.database import Base
from app.migrate import upgrade_database
from app.main import app
from app.models.equipment import Criticality, Equipment, EquipmentSystem
from app.models.route import InspectionPoint, InspectionRoute
from app.models.task import InspectionTask
from app.models.user import User, UserRole


@pytest.fixture
def pg_engine():
    url = os.environ.get('TEST_POSTGRESQL_URL')
    if not url:
        pytest.skip('Set TEST_POSTGRESQL_URL to run real PostgreSQL integration tests')
    if make_url(url).get_backend_name() != 'postgresql':
        pytest.fail('TEST_POSTGRESQL_URL must point to PostgreSQL')
    schema = f'ei_test_{uuid4().hex}'
    admin = create_engine(url, connect_args={'connect_timeout': 5})
    engine = create_engine(url, connect_args={
        'connect_timeout': 5,
        'options': f'-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=15000',
    })
    created = False
    try:
        with admin.begin() as conn:
            conn.execute(CreateSchema(schema))
        created = True
        upgrade_database(engine)
        yield engine
    finally:
        engine.dispose()
        try:
            if created:
                with admin.begin() as conn:
                    conn.execute(DropSchema(schema, cascade=True))
        finally:
            admin.dispose()


@pytest.fixture
def pg_context(pg_engine, monkeypatch):
    # Do not enter TestClient's lifespan: it starts the application database and scheduler.
    monkeypatch.setattr(settings, 'SAFETY_SYSTEM_URL', '')
    monkeypatch.setattr(settings, 'PROCUREMENT_SYSTEM_URL', '')
    monkeypatch.setattr(settings, 'SECRET_KEY', 'isolated-postgresql-test-signing-key')
    factory = sessionmaker(bind=pg_engine, autoflush=False)
    with factory() as db:
        equipment = Equipment(code='PG-EQ', name='测试泵', equipment_system=EquipmentSystem.AUXILIARY,
                              criticality=Criticality.B, health_score=100)
        route = InspectionRoute(route_no='PG-RT', name='测试路线')
        db.add_all([equipment, route])
        db.add_all([
            User(username=name, role=role, is_active=True, hashed_password='unused-token-test')
            for name, role in [('inspector', UserRole.INSPECTOR), ('other', UserRole.INSPECTOR),
                               ('viewer', UserRole.VIEWER), ('supervisor', UserRole.SUPERVISOR)]
        ])
        db.flush()
        point = InspectionPoint(point_no='PG-PT', route_id=route.id, equipment_id=equipment.id, check_items=[])
        tasks = [InspectionTask(task_no=f'PG-TK-{i}', route_id=route.id, scheduled_at=datetime.utcnow())
                 for i in range(2)]
        db.add_all([point, *tasks])
        db.commit()
        context = SimpleNamespace(engine=pg_engine, factory=factory, equipment_id=equipment.id,
                                  point_id=point.id, task_ids=[t.id for t in tasks])

    def test_db():
        with factory() as db:
            yield db

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = test_db
    context.headers = {'Authorization': f'Bearer {create_access_token("inspector")}'}
    context.supervisor_headers = {'Authorization': f'Bearer {create_access_token("supervisor")}'}
    context.client = TestClient(app, raise_server_exceptions=False, headers=context.headers)
    context.payload = {'point_id': context.point_id, 'status': 'ABNORMAL',
                       'finding': '温度偏高', 'readings': {'temperature': 85}}
    try:
        yield context
    finally:
        context.client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
