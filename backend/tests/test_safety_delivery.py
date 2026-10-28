"""真实临时 HTTP/两数据库：持久消息、严格回执、会话重启与竞争。"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Barrier, Event, Thread
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.api.deps import create_access_token, get_db
from app.config import settings
from app.database import Base
from app.integration.safety_client import mark_pending, push_one, retry_pending
from app.main import app
from app.models.defect import Defect, DefectSeverity
from app.models.equipment import Equipment, EquipmentSystem, Criticality
from app.models.safety_outbox import SafetyOutbox
from app.models.user import User, UserRole
from tests.postgresql.conftest import pg_engine  # noqa: F401


@pytest.fixture(params=['sqlite', 'postgresql'])
def delivery_ctx(request, tmp_path, monkeypatch):
    if request.param == 'postgresql':
        engine = request.getfixturevalue('pg_engine')
    else:
        engine = create_engine(f'sqlite:///{tmp_path / "delivery.db"}', connect_args={'check_same_thread': False})
        Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(settings, 'SECRET_KEY', 'delivery-token-test-key')
    monkeypatch.setattr(settings, 'INTEGRATION_SECRET', 'delivery-shared-test-key')
    monkeypatch.setattr(settings, 'SAFETY_SYSTEM_URL', '')
    monkeypatch.setattr(settings, 'INTEGRATION_TIMEOUT_SEC', 1)
    with factory() as db:
        equipment = Equipment(code='EQ-BL-DELIVERY', name='测试锅炉', equipment_system=EquipmentSystem.BOILER,
                              criticality=Criticality.A, health_score=100)
        db.add(equipment)
        db.add(User(username='delivery', role=UserRole.SUPERVISOR, is_active=True, hashed_password='unused'))
        db.commit()
        equipment_id = equipment.id
    def sessions():
        with factory() as db:
            yield db
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = sessions
    client = TestClient(app, raise_server_exceptions=False,
                        headers={'Authorization': 'Bearer '+create_access_token('delivery')})
    ctx = SimpleNamespace(engine=engine, factory=factory, client=client, equipment_id=equipment_id)
    try:
        yield ctx
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        if request.param == 'sqlite':
            engine.dispose()


def defect(ctx, *, mark=False, status='PENDING'):
    with ctx.factory() as db:
        d = Defect(defect_no='DF-DELIVERY-001', equipment_id=ctx.equipment_id,
                   severity=DefectSeverity.CRITICAL, title='原始关键缺陷', description='原始测点异常',
                   reported_by='delivery', reported_at=datetime(2026, 10, 12, 12),
                   safety_sync_status=status)
        db.add(d)
        db.flush()
        if mark:
            mark_pending(db, d)
        db.commit()
        return d.id


@contextmanager
def peer(monkeypatch, *, status=200, override=None, hold=False, close_first=False, inspect=None):
    remote = SimpleNamespace(requests=[], visible=[], entered=Event(), release=Event())
    if not hold:
        remote.release.set()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            remote.requests.append(body)
            if inspect:
                remote.visible.append(inspect(body))
            remote.entered.set()
            if not remote.release.wait(timeout=5):
                self.send_error(504)
                return
            if close_first and len(remote.requests) == 1:
                self.connection.close()
                return
            response = {'code': 200, 'data': {'id': 1, 'hazard_no': 'YH-20261012-0001',
                                             'source_system': body['source_system'], 'external_no': body['external_no']}}
            if override is not None:
                response = override(response)
            encoded = response if isinstance(response, bytes) else json.dumps(response).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    monkeypatch.setattr(settings, 'SAFETY_SYSTEM_URL', f'http://127.0.0.1:{server.server_port}')
    thread.start()
    try:
        yield remote
    finally:
        remote.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def deliver(ctx, did):
    with ctx.factory() as db:
        return push_one(db, db.get(Defect, did))


@pytest.mark.parametrize('case', ['empty', 'bad-json', 'business-error', 'missing-id', 'bool-id',
                                 'missing-number', 'long-number', 'wrong-source', 'wrong-key'])
def test_invalid_ack_never_marks_synced(delivery_ctx, monkeypatch, case):
    ctx = delivery_ctx
    def malformed(body):
        if case == 'empty': return {}
        if case == 'bad-json': return b'not-json'
        if case == 'business-error': body['code'] = 503
        if case == 'missing-id': body['data'].pop('id')
        if case == 'bool-id': body['data']['id'] = True
        if case == 'missing-number': body['data']['hazard_no'] = ''
        if case == 'long-number': body['data']['hazard_no'] = 'x'*51
        if case == 'wrong-source': body['data']['source_system'] = 'other'
        if case == 'wrong-key': body['data']['external_no'] = 'other'
        return body
    with peer(monkeypatch, override=malformed):
        did = defect(ctx)
        assert deliver(ctx, did) is False
    with ctx.factory() as db:
        d = db.get(Defect, did)
        assert d.safety_sync_status == 'FAILED'
        assert d.safety_hazard_no is None
        assert d.safety_sync_attempts == 1
        assert d.safety_sync_error


@pytest.mark.parametrize('status', [202, 302, 409, 503])
def test_non200_status_and_remote_private_body_are_controlled(delivery_ctx, monkeypatch, status):
    ctx = delivery_ctx
    with peer(monkeypatch, status=status, override=lambda _: {'message': 'private-server-password-marker'}):
        did = defect(ctx)
        assert deliver(ctx, did) is False
    with ctx.factory() as db:
        d = db.get(Defect, did)
        assert d.safety_sync_status == 'FAILED'
        assert 'private-server-password-marker' not in d.safety_sync_error


def test_mark_pending_message_is_visible_before_http(delivery_ctx, monkeypatch):
    ctx = delivery_ctx
    def stored(body):
        with ctx.factory() as db:
            row = db.query(SafetyOutbox).first()
            return row.payload if row else None
    with peer(monkeypatch, inspect=stored) as remote:
        response = ctx.client.post('/api/defects', json={'equipment_id': ctx.equipment_id,
                                   'title': '真实 API 紧急缺陷', 'description': '持久原始描述', 'severity': 'CRITICAL'})
        assert response.status_code == 200, response.text
        assert remote.visible == remote.requests
        assert remote.requests[0]['title'] == '真实 API 紧急缺陷'
    with ctx.factory() as db:
        assert db.query(Defect).one().safety_sync_status == 'SYNCED'
        assert db.query(SafetyOutbox).count() == 1


def test_lost_reply_and_new_session_retry_original_frozen_payload(delivery_ctx, monkeypatch):
    ctx = delivery_ctx
    with peer(monkeypatch, close_first=True) as remote:
        did = defect(ctx, mark=True)
        assert deliver(ctx, did) is False
        with ctx.factory() as db:
            db.get(Defect, did).description = '后来修订的描述'
            db.get(Equipment, ctx.equipment_id).name = '后来改名的设备'
            db.commit()
        assert deliver(ctx, did) is True
        assert len(remote.requests) == 2
        assert remote.requests[0] == remote.requests[1]
    with ctx.factory() as db:
        assert db.get(Defect, did).safety_sync_attempts == 2
        assert db.get(SafetyOutbox, did).payload == remote.requests[0]


def test_two_stale_sessions_complete_one_delivery(delivery_ctx, monkeypatch):
    ctx = delivery_ctx
    start = Barrier(2)
    with peer(monkeypatch, hold=True) as remote:
        did = defect(ctx, mark=True)
        def send():
            with ctx.factory() as db:
                d = db.get(Defect, did)
                start.wait(timeout=5)
                return push_one(db, d)
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(send) for _ in range(2)]
            assert remote.entered.wait(timeout=5)
            remote.release.set()
            assert all(job.result(timeout=10) is True for job in jobs)
        assert len(remote.requests) == 1
    with ctx.factory() as db:
        assert db.get(Defect, did).safety_sync_attempts == 1


def test_fake_legacy_synced_without_reference_is_not_trusted(delivery_ctx, monkeypatch):
    ctx = delivery_ctx
    with peer(monkeypatch) as remote:
        did = defect(ctx, status='SYNCED')
        assert deliver(ctx, did) is True
        assert len(remote.requests) == 1
    with ctx.factory() as db:
        assert db.get(Defect, did).safety_hazard_no == 'YH-20261012-0001'


def test_retry_scans_committed_failed_payloads(delivery_ctx, monkeypatch):
    ctx = delivery_ctx
    with peer(monkeypatch, status=503):
        did = defect(ctx, mark=True)
        assert deliver(ctx, did) is False
    with peer(monkeypatch) as remote:
        with ctx.factory() as db:
            result = retry_pending(db)
        assert result == {'scanned': 1, 'synced': 1, 'failed': 0}
        assert len(remote.requests) == 1


def test_ack_local_write_failure_is_not_success_and_can_replay(delivery_ctx, monkeypatch):
    ctx = delivery_ctx
    def fail_ack_save(conn, cursor, statement, parameters, context, many):
        if statement.lower().startswith('update defects') and context.compiled_parameters:
            if context.compiled_parameters[0].get('safety_sync_status') == 'SYNCED':
                conn.exec_driver_sql('SELECT * FROM intentional_missing_delivery_ack_table')
    with peer(monkeypatch) as remote:
        did = defect(ctx, mark=True)
        event.listen(ctx.engine, 'before_cursor_execute', fail_ack_save)
        try:
            assert deliver(ctx, did) is False
        finally:
            event.remove(ctx.engine, 'before_cursor_execute', fail_ack_save)
        with ctx.factory() as db:
            assert db.get(Defect, did).safety_sync_status != 'SYNCED'
        assert deliver(ctx, did) is True
        assert len(remote.requests) == 2 and remote.requests[0] == remote.requests[1]


def test_missing_endpoint_still_freezes_original_critical_message(delivery_ctx, monkeypatch):
    ctx = delivery_ctx
    did = defect(ctx, mark=True)
    with ctx.factory() as db:
        db.get(Defect, did).description = '配置端点前修改了说明'
        db.commit()
    with peer(monkeypatch) as remote:
        assert deliver(ctx, did) is True
        assert remote.requests[0]['description'] == '原始测点异常'


@pytest.mark.parametrize('reference', [None, '', ' ', '\t', '\n', 'bad\tref'])
def test_retry_recovers_all_invalid_legacy_references(delivery_ctx, monkeypatch, reference):
    ctx = delivery_ctx
    did = defect(ctx, status='SYNCED')
    with ctx.factory() as db:
        db.get(Defect, did).safety_hazard_no = reference
        db.commit()
    with peer(monkeypatch) as remote:
        with ctx.factory() as db:
            assert retry_pending(db, limit=1) == {'scanned': 1, 'synced': 1, 'failed': 0}
        assert len(remote.requests) == 1
    with ctx.factory() as db:
        assert db.get(Defect, did).safety_hazard_no == 'YH-20261012-0001'


def test_good_historical_reference_does_not_starve_recovery_limit(delivery_ctx, monkeypatch):
    ctx = delivery_ctx
    good_id = defect(ctx, status='SYNCED')
    with ctx.factory() as db:
        db.get(Defect, good_id).safety_hazard_no = 'YH-VALID-OLD'
        invalid = Defect(defect_no='DF-INVALID-002', equipment_id=ctx.equipment_id,
                         severity=DefectSeverity.CRITICAL, title='旧假成功', reported_by='delivery',
                         safety_sync_status='SYNCED', safety_hazard_no='bad\tref')
        db.add(invalid)
        db.commit()
        invalid_id = invalid.id
    with peer(monkeypatch) as remote:
        with ctx.factory() as db:
            assert retry_pending(db, limit=1) == {'scanned': 1, 'synced': 1, 'failed': 0}
        assert len(remote.requests) == 1 and remote.requests[0]['external_no'] == 'DF-INVALID-002'
    with ctx.factory() as db:
        assert db.get(Defect, good_id).safety_sync_attempts == 0
        assert db.get(Defect, invalid_id).safety_sync_status == 'SYNCED'


@pytest.mark.parametrize('status,reason', [('SKIPPED', 'SAFETY_SYSTEM_URL 未配置'), ('FAILED', '网络请求失败（ConnectError）'), ('SYNCED', None)])
def test_daily_defect_reads_preserve_saved_sync_reason(delivery_ctx, status, reason):
    ctx = delivery_ctx
    did = defect(ctx, status=status)
    with ctx.factory() as db:
        db.get(Defect, did).safety_sync_error = reason
        db.commit()
    detail = ctx.client.get(f'/api/defects/{did}')
    listing = ctx.client.get('/api/defects')
    assert detail.status_code == listing.status_code == 200
    assert detail.json()['data']['safety_sync_error'] == reason
    assert listing.json()['data']['items'][0]['safety_sync_error'] == reason
