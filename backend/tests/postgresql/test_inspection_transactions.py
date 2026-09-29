"""Inspect real committed API results, including deliberately overlapping transactions."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.deps import create_access_token
from app.models.defect import Defect
from app.models.equipment import Equipment, EquipmentStatus
from app.models.task import InspectionRecord, InspectionTask, TaskStatus
from app.record_schema import ensure_record_uniqueness
from .concurrency import overlap_initial_reads, post_concurrently


def test_concurrent_identical_replays_have_one_business_effect(pg_context):
    ctx = pg_context
    request = (f'/api/tasks/{ctx.task_ids[0]}/records', ctx.payload)
    responses = post_concurrently(ctx, [request, request])
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    assert responses[0].json()['data'] == responses[1].json()['data']
    with ctx.factory() as db:
        assert db.query(InspectionRecord).count() == 1
        assert db.query(Defect).count() == 1
        assert db.get(Equipment, ctx.equipment_id).health_score == 97
        task = db.get(InspectionTask, ctx.task_ids[0])
        assert task.abnormal_count == 1
        assert task.status == TaskStatus.COMPLETED


def test_concurrent_conflict_keeps_the_winning_content(pg_context):
    ctx = pg_context
    path = f'/api/tasks/{ctx.task_ids[0]}/records'
    responses = post_concurrently(ctx, [(path, ctx.payload), (path, {**ctx.payload, 'finding': '不同观察'})])
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    winner = next(r.json()['data'] for r in responses if r.status_code == 200)
    with ctx.factory() as db:
        record = db.query(InspectionRecord).one()
        assert record.finding == winner['finding']
        assert db.query(Defect).count() == 1
        assert db.get(Equipment, ctx.equipment_id).health_score == 97


@pytest.mark.parametrize(('username', 'expected_status'), [('other', 409), ('viewer', 403)])
def test_replay_does_not_bypass_account_or_role_checks(pg_context, username, expected_status):
    ctx = pg_context
    path = f'/api/tasks/{ctx.task_ids[0]}/records'
    assert ctx.client.post(path, json=ctx.payload).status_code == 200
    response = ctx.client.post(path, json=ctx.payload,
                               headers={'Authorization': f'Bearer {create_access_token(username)}'})
    assert response.status_code == expected_status
    with ctx.factory() as db:
        assert db.query(InspectionRecord).one().recorded_by == 'inspector'
        assert db.query(Defect).count() == 1
        assert db.get(Equipment, ctx.equipment_id).health_score == 97


@pytest.mark.parametrize(('point_status', 'score', 'equipment_status'), [
    ('ABNORMAL', 94, EquipmentStatus.RUNNING),
    ('SEVERE', 84, EquipmentStatus.MAINTENANCE),
])
def test_different_tasks_accumulate_health_deductions_without_number_collision(
    pg_context, point_status, score, equipment_status,
):
    ctx = pg_context
    body = {**ctx.payload, 'status': point_status}
    with overlap_initial_reads(ctx.engine):
        responses = post_concurrently(ctx, [(f'/api/tasks/{tid}/records', body) for tid in ctx.task_ids])
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    with ctx.factory() as db:
        assert db.query(InspectionRecord).count() == 2
        defects = db.query(Defect).all()
        assert len(defects) == 2
        assert len({d.defect_no for d in defects}) == 2
        assert db.get(Equipment, ctx.equipment_id).health_score == score
        assert db.get(Equipment, ctx.equipment_id).status == equipment_status
        assert all(t.status == TaskStatus.COMPLETED and t.abnormal_count == 1
                   for t in db.query(InspectionTask).all())


@pytest.mark.parametrize('mixed_sources', [False, True])
def test_manual_and_inspection_defect_numbers_do_not_race(pg_context, mixed_sources):
    ctx = pg_context
    manual = ('/api/defects', {'equipment_id': ctx.equipment_id, 'title': '人工上报'})
    other = (f'/api/tasks/{ctx.task_ids[0]}/records', ctx.payload) if mixed_sources else manual
    with overlap_initial_reads(ctx.engine):
        responses = post_concurrently(ctx, [manual, other])
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    with ctx.factory() as db:
        defects = db.query(Defect).all()
        assert len(defects) == 2
        assert len({d.defect_no for d in defects}) == 2
        assert all(len(d.defect_no) <= 50 for d in defects)
        assert db.query(InspectionRecord).count() == int(mixed_sources)
        assert db.get(Equipment, ctx.equipment_id).health_score == (97 if mixed_sources else 100)


@pytest.mark.parametrize(('initial', 'expected'), [(0, 0), (2, 0), (None, 97)])
def test_health_boundary_and_null_default(pg_context, initial, expected):
    ctx = pg_context
    with ctx.factory() as db:
        db.get(Equipment, ctx.equipment_id).health_score = initial
        db.commit()
    response = ctx.client.post(f'/api/tasks/{ctx.task_ids[0]}/records', json=ctx.payload)
    assert response.status_code == 200, response.text
    with ctx.factory() as db:
        assert db.get(Equipment, ctx.equipment_id).health_score == expected


@pytest.mark.parametrize(('table', 'condition'), [
    ('defects', "title <> '[点检] 测试泵 - 温度偏高'"),
    ('inspection_tasks', "status <> 'COMPLETED'"),
])
def test_failed_write_rolls_back_record_health_and_task_and_allows_retry(pg_context, table, condition):
    ctx = pg_context
    with ctx.engine.begin() as conn:
        # Literals supplied by this test, never application input. The task constraint
        # fails at commit, after the record, defect and atomic health update executed.
        conn.execute(text(f'ALTER TABLE {table} ADD CONSTRAINT test_reject_write CHECK ({condition})'))
    path = f'/api/tasks/{ctx.task_ids[0]}/records'
    assert ctx.client.post(path, json=ctx.payload).status_code == 500
    with ctx.factory() as db:
        assert db.query(InspectionRecord).count() == 0
        assert db.query(Defect).count() == 0
        task = db.get(InspectionTask, ctx.task_ids[0])
        assert task.status == TaskStatus.PENDING
        assert task.abnormal_count == 0
        assert db.get(Equipment, ctx.equipment_id).health_score == 100
    with ctx.engine.begin() as conn:
        conn.execute(text(f'ALTER TABLE {table} DROP CONSTRAINT test_reject_write'))
    assert ctx.client.post(path, json=ctx.payload).status_code == 200
    with ctx.factory() as db:
        assert db.query(InspectionRecord).count() == 1
        assert db.query(Defect).count() == 1
        assert db.get(Equipment, ctx.equipment_id).health_score == 97


def test_record_unique_index_upgrade_is_repeatable(pg_context):
    ctx = pg_context
    assert ctx.client.post(f'/api/tasks/{ctx.task_ids[0]}/records', json=ctx.payload).status_code == 200
    with ctx.engine.begin() as conn:
        conn.execute(text('DROP INDEX uq_inspection_record_task_point'))
    ensure_record_uniqueness(ctx.engine)
    ensure_record_uniqueness(ctx.engine)
    with ctx.factory() as db:
        db.add(InspectionRecord(task_id=ctx.task_ids[0], point_id=ctx.point_id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        assert db.query(InspectionRecord).count() == 1


def test_index_upgrade_preserves_legacy_duplicates(pg_context):
    ctx = pg_context
    with ctx.engine.begin() as conn:
        conn.execute(text('DROP INDEX uq_inspection_record_task_point'))
    with ctx.factory() as db:
        db.add_all([InspectionRecord(task_id=ctx.task_ids[0], point_id=ctx.point_id) for _ in range(2)])
        db.commit()
    with pytest.raises(RuntimeError, match='task_id='):
        ensure_record_uniqueness(ctx.engine)
    with ctx.factory() as db:
        assert db.query(InspectionRecord).count() == 2
