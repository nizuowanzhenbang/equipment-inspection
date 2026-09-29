"""Real login/JWT and database effects for the five business roles."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.config import settings
from app.api.deps import get_db, hash_password
from app.database import Base
from app.models.audit import AuditLog
from app.models.user import User, UserRole
from app.models.equipment import Equipment, EquipmentSystem, Criticality
from app.models.route import InspectionRoute, InspectionPoint
from app.models.task import InspectionTask, InspectionRecord
from app.models.defect import Defect, DefectStatus


PASSWORD = 'role-test-password-only'


@pytest.fixture(scope='module')
def encoded_password():
    return hash_password(PASSWORD)


@pytest.fixture
def role_context(tmp_path, monkeypatch, encoded_password):
    monkeypatch.setattr(settings, 'APP_MODE', 'production')
    engine = create_engine(f'sqlite:///{(tmp_path / "roles.db").as_posix()}',
                           connect_args={'check_same_thread': False})
    factory = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    with factory() as db:
        db.add_all([User(username=role.value.lower(), role=role, hashed_password=encoded_password)
                    for role in UserRole])
        db.add(User(username='disabled', role=UserRole.ADMIN, hashed_password=encoded_password, is_active=False))
        equipment = Equipment(code='TEST', name='test', equipment_system=EquipmentSystem.BOILER,
                              criticality=Criticality.B, health_score=80)
        route = InspectionRoute(route_no='TEST', name='test')
        db.add_all([equipment, route])
        db.flush()
        point = InspectionPoint(point_no='TEST', route_id=route.id, equipment_id=equipment.id, check_items=[])
        task = InspectionTask(task_no='TEST', route_id=route.id, scheduled_at=datetime.utcnow())
        defect = Defect(defect_no='TEST', equipment_id=equipment.id, title='test')
        db.add_all([point, task, defect])
        db.commit()
        ctx = SimpleNamespace(factory=factory, did=defect.id, tid=task.id, pid=point.id,
                              original_hash=encoded_password,
                              viewer_id=db.query(User).filter_by(username='viewer').one().id,
                              admin_id=db.query(User).filter_by(username='admin').one().id)

    def sessions():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = sessions
    ctx.client = TestClient(app)
    try:
        yield ctx
    finally:
        ctx.client.close()
        app.dependency_overrides.clear()
        engine.dispose()


def login(ctx, role):
    response = ctx.client.post('/api/auth/login', data={'username': role, 'password': PASSWORD})
    assert response.status_code == 200, response.text
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


CASES = [
    ('record', {'admin', 'inspector'}),
    ('assign', {'admin', 'supervisor'}),
    ('start-repair', {'admin', 'repairman'}),
    ('repair', {'admin', 'repairman'}),
    ('verify', {'admin', 'supervisor'}),
    ('list-users', {'admin'}),
    ('create-user', {'admin'}),
    ('update-user', {'admin'}),
    ('reset-password', {'admin'}),
    ('toggle-active', {'admin'}),
]


@pytest.mark.parametrize('role', [r.value.lower() for r in UserRole])
@pytest.mark.parametrize(('action', 'allowed'), CASES)
def test_role_matrix(role_context, role, action, allowed):
    ctx = role_context
    initial = {'start-repair': DefectStatus.ASSIGNED, 'repair': DefectStatus.IN_REPAIR,
               'verify': DefectStatus.REPAIRED}.get(action, DefectStatus.NEW)
    with ctx.factory() as db:
        db.get(Defect, ctx.did).status = initial
        db.commit()
    requests = {
        'record': ('POST', f'/api/tasks/{ctx.tid}/records', {'point_id': ctx.pid, 'status': 'NORMAL'}),
        'assign': ('POST', f'/api/defects/{ctx.did}/assign', {'assigned_to': 'repairman'}),
        'start-repair': ('POST', f'/api/defects/{ctx.did}/start-repair', {}),
        'repair': ('POST', f'/api/defects/{ctx.did}/repair', {'repair_notes': 'done'}),
        'verify': ('POST', f'/api/defects/{ctx.did}/verify', {'pass_': True}),
        'list-users': ('GET', '/api/users', None),
        'create-user': ('POST', '/api/users', {'username': 'new-person', 'password': PASSWORD}),
        'update-user': ('PUT', f'/api/users/{ctx.viewer_id}', {'full_name': 'Changed'}),
        'reset-password': ('POST', f'/api/users/{ctx.viewer_id}/reset-password', {'new_password': 'new-password-for-test'}),
        'toggle-active': ('POST', f'/api/users/{ctx.viewer_id}/toggle-active', {}),
    }
    method, path, body = requests[action]
    response = ctx.client.request(method, path, json=body, headers=login(ctx, role))
    assert response.status_code == (200 if role in allowed else 403), response.text
    with ctx.factory() as db:
        if role not in allowed:
            assert db.get(Defect, ctx.did).status == initial
            assert db.query(InspectionRecord).count() == 0
            assert db.query(User).count() == 6
            assert db.query(AuditLog).count() == 0
            viewer = db.get(User, ctx.viewer_id)
            assert viewer.full_name is None and viewer.is_active
            assert viewer.hashed_password == ctx.original_hash
        elif action in ('assign', 'start-repair', 'repair', 'verify'):
            expected = {'assign': DefectStatus.ASSIGNED, 'start-repair': DefectStatus.IN_REPAIR,
                        'repair': DefectStatus.REPAIRED, 'verify': DefectStatus.CLOSED}
            assert db.get(Defect, ctx.did).status == expected[action]
        elif action == 'record':
            assert db.query(InspectionRecord).count() == 1


def test_revoked_account_and_forged_token_cannot_use_admin_api(role_context):
    ctx = role_context
    headers = login(ctx, 'admin')
    with ctx.factory() as db:
        db.get(User, ctx.admin_id).is_active = False
        db.commit()
    assert ctx.client.get('/api/users', headers=headers).status_code == 401
    assert ctx.client.get('/api/users', headers={'Authorization': 'Bearer forged'}).status_code == 401
    assert ctx.client.get('/api/users').status_code == 401
    assert ctx.client.post('/api/auth/login', data={'username': 'disabled', 'password': PASSWORD}).status_code == 403


@pytest.mark.parametrize('action', ['create', 'reset'])
@pytest.mark.parametrize('password', ['short1', 'x' * 73, '密' * 25])
def test_production_password_policy(role_context, action, password):
    ctx = role_context
    headers = login(ctx, 'admin')
    path = '/api/users' if action == 'create' else f'/api/users/{ctx.viewer_id}/reset-password'
    body = {'username': 'new-person', 'password': password} if action == 'create' else {'new_password': password}
    assert ctx.client.post(path, json=body, headers=headers).status_code == 400
    with ctx.factory() as db:
        assert db.query(User).count() == 6
        assert db.query(AuditLog).count() == 0


def test_custom_admin_cannot_demote_self(role_context):
    ctx = role_context
    with ctx.factory() as db:
        db.get(User, ctx.admin_id).username = 'custom-operator'
        db.commit()
    response = ctx.client.put(f'/api/users/{ctx.admin_id}', json={'role': 'VIEWER'},
                              headers=login(ctx, 'custom-operator'))
    assert response.status_code == 400
