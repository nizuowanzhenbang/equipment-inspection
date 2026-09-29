"""Real verification races: one decision, no lost health changes, correct equipment state."""
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from app.models.audit import AuditLog
from app.models.defect import Defect, DefectSeverity, DefectStatus
from app.models.equipment import Equipment, EquipmentStatus
from .concurrency import overlap_initial_reads, pause_next_read, post_concurrently, post_request


def prepare(context, count=1, health=80):
    with context.factory() as db:
        equipment = db.get(Equipment, context.equipment_id)
        equipment.health_score = health
        equipment.status = EquipmentStatus.MAINTENANCE
        defects = [Defect(defect_no=f'VERIFY-{i}', equipment_id=equipment.id, title='待验收缺陷',
                          status=DefectStatus.REPAIRED, severity=DefectSeverity.MINOR) for i in range(count)]
        db.add_all(defects)
        db.commit()
        return [d.id for d in defects]


def verify_request(context, defect_id, passed=True):
    return (f'/api/defects/{defect_id}/verify', {'pass_': passed, 'verify_notes': '测试验收'},
            context.supervisor_headers)


@pytest.mark.parametrize('second_passes', [True, False])
def test_same_defect_accepts_one_concurrent_decision(pg_context, second_passes):
    ctx = pg_context
    did = prepare(ctx)[0]
    with overlap_initial_reads(ctx.engine):
        responses = post_concurrently(ctx, [verify_request(ctx, did), verify_request(ctx, did, second_passes)])
    assert sorted(r.status_code for r in responses) == [200, 400], [r.text for r in responses]
    with ctx.factory() as db:
        defect = db.get(Defect, did)
        equipment = db.get(Equipment, ctx.equipment_id)
        audit = db.query(AuditLog).one()
        if responses[0].status_code == 200 or second_passes:
            assert defect.status == DefectStatus.CLOSED
            assert equipment.health_score == 83
            assert equipment.status == EquipmentStatus.RUNNING
            assert audit.action == 'defect.verify_pass'
        else:
            assert defect.status == DefectStatus.IN_REPAIR
            assert equipment.health_score == 80
            assert equipment.status == EquipmentStatus.MAINTENANCE
            assert audit.action == 'defect.verify_reject'


def test_different_defects_accumulate_recovery_and_last_one_restores_running(pg_context):
    ctx = pg_context
    ids = prepare(ctx, count=2)
    with overlap_initial_reads(ctx.engine):
        responses = post_concurrently(ctx, [verify_request(ctx, did) for did in ids])
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    with ctx.factory() as db:
        assert all(d.status == DefectStatus.CLOSED for d in db.query(Defect))
        assert db.get(Equipment, ctx.equipment_id).health_score == 86
        assert db.get(Equipment, ctx.equipment_id).status == EquipmentStatus.RUNNING
        assert db.query(AuditLog).count() == 2


def test_verification_refreshes_health_after_an_inspection_commits(pg_context):
    ctx = pg_context
    did = prepare(ctx)[0]
    with pause_next_read(ctx.engine, 'from defects left outer join equipments') as (reached, release):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(post_request, ctx, verify_request(ctx, did))
            try:
                assert reached.wait(timeout=10), 'Verification did not read its initial snapshot'
                response = ctx.client.post(f'/api/tasks/{ctx.task_ids[0]}/records', json=ctx.payload)
                assert response.status_code == 200, response.text
            finally:
                release.set()
            result = pending.result(timeout=15)
    assert result.status_code == 200, result.text
    with ctx.factory() as db:
        assert db.get(Equipment, ctx.equipment_id).health_score == 80  # 80 - 3 + 3
        assert db.get(Equipment, ctx.equipment_id).status == EquipmentStatus.MAINTENANCE
        assert db.get(Defect, did).status == DefectStatus.CLOSED
        assert db.query(AuditLog).count() == 1


def test_severe_inspection_refreshes_status_after_verification_restores_running(pg_context):
    ctx = pg_context
    did = prepare(ctx)[0]
    inspection = (f'/api/tasks/{ctx.task_ids[0]}/records', {**ctx.payload, 'status': 'SEVERE'})
    with pause_next_read(ctx.engine, 'from inspection_points left outer join equipments') as (reached, release):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(post_request, ctx, inspection)
            try:
                assert reached.wait(timeout=10), 'Inspection did not read its initial snapshot'
                result = post_request(ctx, verify_request(ctx, did))
                assert result.status_code == 200, result.text
            finally:
                release.set()
            response = pending.result(timeout=15)
    assert response.status_code == 200, response.text
    with ctx.factory() as db:
        assert db.get(Equipment, ctx.equipment_id).health_score == 75  # 80 + 3 - 8
        assert db.get(Equipment, ctx.equipment_id).status == EquipmentStatus.MAINTENANCE


@pytest.mark.parametrize('autoflush', [True, False])
def test_other_unclosed_defect_prevents_restoring_running(pg_context, autoflush):
    ctx = pg_context
    ids = prepare(ctx, count=2)
    ctx.factory.configure(autoflush=autoflush)
    response = post_request(ctx, verify_request(ctx, ids[0]))
    assert response.status_code == 200, response.text
    with ctx.factory() as db:
        assert db.get(Equipment, ctx.equipment_id).status == EquipmentStatus.MAINTENANCE
        assert db.get(Equipment, ctx.equipment_id).health_score == 83
        assert db.get(Defect, ids[1]).status == DefectStatus.REPAIRED


@pytest.mark.parametrize(('initial', 'expected'), [(98, 100), (0, 3), (None, 3)])
def test_recovery_respects_upper_bound_and_null_default(pg_context, initial, expected):
    ctx = pg_context
    did = prepare(ctx, health=initial)[0]
    response = post_request(ctx, verify_request(ctx, did))
    assert response.status_code == 200, response.text
    with ctx.factory() as db:
        assert db.get(Equipment, ctx.equipment_id).health_score == expected


def test_failed_verification_rolls_back_health_status_and_audit(pg_context):
    ctx = pg_context
    did = prepare(ctx)[0]
    with ctx.engine.begin() as conn:
        conn.execute(text("ALTER TABLE defects ADD CONSTRAINT test_reject_close CHECK (status <> 'CLOSED')"))
    response = post_request(ctx, verify_request(ctx, did))
    assert response.status_code == 500
    with ctx.factory() as db:
        assert db.get(Defect, did).status == DefectStatus.REPAIRED
        assert db.get(Equipment, ctx.equipment_id).health_score == 80
        assert db.get(Equipment, ctx.equipment_id).status == EquipmentStatus.MAINTENANCE
        assert db.query(AuditLog).count() == 0
    with ctx.engine.begin() as conn:
        conn.execute(text('ALTER TABLE defects DROP CONSTRAINT test_reject_close'))
    assert post_request(ctx, verify_request(ctx, did)).status_code == 200
    with ctx.factory() as db:
        assert db.get(Equipment, ctx.equipment_id).health_score == 83
        assert db.get(Defect, did).status == DefectStatus.CLOSED
        assert db.query(AuditLog).count() == 1


def test_inspector_cannot_verify_defects(pg_context):
    ctx = pg_context
    did = prepare(ctx)[0]
    response = ctx.client.post(f'/api/defects/{did}/verify', json={'pass_': True})
    assert response.status_code == 403
    with ctx.factory() as db:
        assert db.get(Defect, did).status == DefectStatus.REPAIRED
        assert db.get(Equipment, ctx.equipment_id).health_score == 80
        assert db.query(AuditLog).count() == 0
