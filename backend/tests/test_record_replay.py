"""弱网重放必须复用原记录，不重复创建缺陷或扣减健康度。"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.api.deps import get_current_user, get_db
from app.database import Base
from app.models.defect import Defect
from app.models.equipment import Equipment, EquipmentSystem, Criticality
from app.models.route import InspectionRoute, InspectionPoint
from app.models.task import InspectionTask, InspectionRecord, TaskStatus
from app.models.user import User, UserRole
from app.record_schema import ensure_record_uniqueness


@pytest.fixture
def context():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    eq = Equipment(code='EQ-TEST', name='演示设备', equipment_system=EquipmentSystem.BOILER,
                   criticality=Criticality.B, health_score=100)
    route = InspectionRoute(route_no='RT-TEST', name='演示路线')
    db.add_all([eq, route])
    db.flush()
    point = InspectionPoint(point_no='PT-TEST', route_id=route.id, equipment_id=eq.id, check_items=[])
    task = InspectionTask(task_no='TK-TEST', route_id=route.id, scheduled_at=datetime.utcnow())
    db.add_all([point, task])
    db.commit()
    user = User(username='inspector', role=UserRole.INSPECTOR, is_active=True)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app), db, task.id, point.id, eq.id, user
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def payload(pid):
    return {'point_id': pid, 'status': 'ABNORMAL', 'readings': {'temperature': 85}, 'finding': '温度偏高'}


def test_retry_after_task_completed_returns_original_without_side_effects(context):
    client, db, tid, pid, eid, _ = context
    first = client.post(f'/api/tasks/{tid}/records', json=payload(pid))
    assert first.status_code == 200
    second = client.post(f'/api/tasks/{tid}/records', json=payload(pid))
    assert second.status_code == 200
    assert second.json()['data'] == first.json()['data']
    db.expire_all()
    assert db.query(InspectionRecord).count() == 1
    assert db.query(Defect).count() == 1
    assert db.get(Equipment, eid).health_score == 97
    assert db.get(InspectionTask, tid).abnormal_count == 1
    assert db.get(InspectionTask, tid).status == TaskStatus.COMPLETED


@pytest.mark.parametrize('change', [{'finding': '新内容'}, {'readings': {'temperature': 90}}, {'status': 'NORMAL'}])
def test_conflicting_retry_preserves_original_and_returns_409(context, change):
    client, db, tid, pid, _, _ = context
    original = client.post(f'/api/tasks/{tid}/records', json=payload(pid)).json()['data']
    response = client.post(f'/api/tasks/{tid}/records', json={**payload(pid), **change})
    assert response.status_code == 409
    assert db.query(InspectionRecord).one().finding == original['finding']
    assert db.query(Defect).count() == 1


def test_other_user_cannot_claim_a_record_as_their_own_retry(context):
    client, db, tid, pid, _, user = context
    client.post(f'/api/tasks/{tid}/records', json=payload(pid))
    user.username = 'another-inspector'
    assert client.post(f'/api/tasks/{tid}/records', json=payload(pid)).status_code == 409
    assert db.query(InspectionRecord).one().recorded_by == 'inspector'


def test_json_boolean_is_not_a_numeric_reading_on_replay(context):
    client, _, tid, pid, _, _ = context
    first = {**payload(pid), 'readings': {'nested': {'value': True}}}
    assert client.post(f'/api/tasks/{tid}/records', json=first).status_code == 200
    changed = {**first, 'readings': {'nested': {'value': 1}}}
    assert client.post(f'/api/tasks/{tid}/records', json=changed).status_code == 409


def test_viewer_cannot_replay_existing_record(context):
    client, _, tid, pid, _, user = context
    client.post(f'/api/tasks/{tid}/records', json=payload(pid))
    user.role = UserRole.VIEWER
    assert client.post(f'/api/tasks/{tid}/records', json=payload(pid)).status_code == 403


def test_database_rejects_duplicate_task_point_even_without_api(context):
    _, db, tid, pid, _, _ = context
    db.add_all([InspectionRecord(task_id=tid, point_id=pid), InspectionRecord(task_id=tid, point_id=pid)])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_upgrade_existing_database_is_repeatable_and_prevents_duplicates():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE inspection_records (id INTEGER PRIMARY KEY, task_id INTEGER, point_id INTEGER)')
        conn.exec_driver_sql('INSERT INTO inspection_records VALUES (1, 10, 20)')
    ensure_record_uniqueness(engine)
    ensure_record_uniqueness(engine)
    with engine.begin() as conn:
        with pytest.raises(IntegrityError):
            conn.exec_driver_sql('INSERT INTO inspection_records VALUES (2, 10, 20)')
    engine.dispose()


def test_upgrade_refuses_to_delete_legacy_duplicates():
    engine = create_engine('sqlite://')
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE inspection_records (id INTEGER PRIMARY KEY, task_id INTEGER, point_id INTEGER)')
        conn.exec_driver_sql('INSERT INTO inspection_records VALUES (1, 10, 20), (2, 10, 20)')
    with pytest.raises(RuntimeError, match='task_id=10'):
        ensure_record_uniqueness(engine)
    with engine.connect() as conn:
        assert conn.exec_driver_sql('SELECT count(*) FROM inspection_records').scalar() == 2
    engine.dispose()


def test_concurrent_retries_commit_one_record_and_one_defect(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    engine = create_engine(f'sqlite:///{tmp_path / "concurrent.db"}', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        eq = Equipment(code='EQ-C', name='设备', equipment_system=EquipmentSystem.BOILER, criticality=Criticality.B)
        route = InspectionRoute(route_no='RT-C', name='路线')
        db.add_all([eq, route])
        db.flush()
        point = InspectionPoint(point_no='PT-C', route_id=route.id, equipment_id=eq.id, check_items=[])
        task = InspectionTask(task_no='TK-C', route_id=route.id, scheduled_at=datetime.utcnow())
        db.add_all([point, task])
        db.commit()
        tid, pid, eid = task.id, point.id, eq.id

    def get_test_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_user] = lambda: User(username='inspector', role=UserRole.INSPECTOR, is_active=True)
    barrier = Barrier(2)

    def submit():
        barrier.wait(timeout=5)
        return TestClient(app).post(f'/api/tasks/{tid}/records', json=payload(pid))

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: submit(), range(2)))
        assert [r.status_code for r in responses] == [200, 200]
        assert responses[0].json()['data']['id'] == responses[1].json()['data']['id']
        with factory() as db:
            assert db.query(InspectionRecord).count() == 1
            assert db.query(Defect).count() == 1
            assert db.get(Equipment, eid).health_score == 97
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
