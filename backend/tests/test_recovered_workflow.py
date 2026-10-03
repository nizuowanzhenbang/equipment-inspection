"""Restore real application data, then continue its lifecycle through authenticated API."""
import json
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backup import backup_database, restore_database
from app.api.deps import get_db
from app.main import app, _create_default_users
from app.migrate import upgrade_database, check_database
from app.models.defect import Defect, DefectStatus, DefectSeverity
from app.models.equipment import Equipment, EquipmentStatus, EquipmentSystem, Criticality
from app.models.route import InspectionRoute, InspectionPoint
from app.models.task import InspectionTask, InspectionRecord, PointStatus
from interview_demo import run_scenario


def recovered_workflow(source_url, target_url, tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'APP_MODE', 'demo')
    monkeypatch.setattr(settings, 'SAFETY_SYSTEM_URL', '')
    monkeypatch.setattr(settings, 'PROCUREMENT_SYSTEM_URL', '')
    source = create_engine(source_url)
    restored = create_engine(target_url)
    try:
        upgrade_database(source)
        factory = sessionmaker(bind=source)
        with factory() as db:
            _create_default_users(db)
            eq = Equipment(code='RESTORE-EQ', name='restored equipment', equipment_system=EquipmentSystem.BOILER,
                           criticality=Criticality.B, health_score=80, status=EquipmentStatus.MAINTENANCE)
            route = InspectionRoute(route_no='RESTORE-RT', name='restored route')
            db.add_all([eq, route])
            db.flush()
            point = InspectionPoint(point_no='RESTORE-PT', route_id=route.id, equipment_id=eq.id, check_items=[])
            task = InspectionTask(task_no='RESTORE-TK', route_id=route.id, scheduled_at=datetime.utcnow())
            defect = Defect(defect_no='RESTORE-DF', equipment_id=eq.id, title='restore proof',
                            severity=DefectSeverity.MINOR, status=DefectStatus.REPAIRED)
            db.add_all([point, task, defect])
            db.flush()
            db.add(InspectionRecord(task_id=task.id, point_id=point.id, defect_id=defect.id,
                                    status=PointStatus.ABNORMAL, finding='preserve this finding'))
            db.commit()
            did, eid = defect.id, eq.id
        archive = tmp_path / 'application.backup'
        manifest = backup_database(source_url, archive)
        restore_database(archive, target_url)
        check_database(restored)
        restored_factory = sessionmaker(bind=restored, autoflush=False)
        with restored_factory() as db:
            record = db.query(InspectionRecord).one()
            assert record.finding == 'preserve this finding'
            assert record.defect.id == did and record.point.equipment.id == eid
            assert db.get(Defect, did).status == DefectStatus.REPAIRED

        def restored_db():
            with restored_factory() as db:
                yield db

        previous = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = restored_db
        client = TestClient(app)
        try:
            login = client.post('/api/auth/login', data={'username': 'supervisor', 'password': 'supervisor123'})
            assert login.status_code == 200
            response = client.post(f'/api/defects/{did}/verify', json={'pass_': True},
                                   headers={'Authorization': 'Bearer ' + login.json()['access_token']})
            assert response.status_code == 200, response.text
            report = run_scenario(client)
            report['scope'] = f'Restored isolated {source.dialect.name} database; real JWT/API, synthetic data'
            assert report['status'] == 'passed'
        finally:
            client.close()
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous)
        with restored_factory() as db:
            assert db.get(Defect, did).status == DefectStatus.CLOSED
            assert db.get(Equipment, eid).health_score == 83
        with factory() as db:
            assert db.get(Defect, did).status == DefectStatus.REPAIRED
            assert db.get(Equipment, eid).health_score == 80
        evidence = {'backend': source.dialect.name, 'backup_sha256': manifest['sha256'],
                    'restored_counts': manifest['tables'], 'existing_defect_closed_after_restore': True,
                    'source_unchanged': True, 'new_workflow': report}
        (tmp_path / 'recovery-evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        source.dispose()
        restored.dispose()


def test_sqlite_recovered_workflow(tmp_path, monkeypatch):
    recovered_workflow(f'sqlite:///{(tmp_path / "source.db").as_posix()}',
                       f'sqlite:///{(tmp_path / "restored.db").as_posix()}', tmp_path, monkeypatch)
