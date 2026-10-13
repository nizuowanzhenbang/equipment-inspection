"""两个独立实际应用/数据库/进程，经过真实 HTTP 和丢回执代理。"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Thread
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import time

import httpx
from jose import jwt
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.migrate import upgrade_database
from app.main import app as registered_app  # noqa: F401 — register all ORM relationships
from app.models.user import User, UserRole
from app.models.equipment import Equipment, EquipmentSystem, Criticality

KEY = 'isolated-contract-jwt-key'
SHARED = 'isolated-contract-shared-key'
ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def application(root, database, logs, *, target=''):
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    environment = dict(os.environ, PYTHONPATH=str(root/'backend'), APP_MODE='demo',
                       DATABASE_URL='sqlite:///'+str(database), SECRET_KEY=KEY,
                       INTEGRATION_SECRET=SHARED, SAFETY_SYSTEM_URL=target,
                       PROCUREMENT_SYSTEM_URL='', SCHEDULER_ENABLED='false',
                       STORAGE_BACKEND='local', UPLOAD_DIR=str(database.parent/'uploads'))
    with logs.open('wb') as output:
        process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app',
                                    '--host', '127.0.0.1', '--port', str(port)],
                                   cwd=root/'backend', env=environment, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic()+20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail(f'isolated service exited; inspect {logs}')
                try:
                    if httpx.get(base+'/health', timeout=.5).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.05)
            else:
                pytest.fail('isolated service did not become ready')
            yield base
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@contextmanager
def forwarding_peer(destination, *, drop_first=False):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            calls.append(json.loads(body))
            response = httpx.post(destination+self.path, content=body, headers={
                'X-Integration-Secret': self.headers.get('X-Integration-Secret', ''),
                'Content-Type': 'application/json'}, timeout=5)
            # 对端应用已 commit 并返回；仅丢弃第一份 ACK，不是模拟假成功。
            if drop_first and len(calls) == 1:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            self.send_response(response.status_code)
            self.send_header('Content-Length', str(len(response.content)))
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(response.content)
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize('lost_ack', [False, True])
def test_actual_apps_recover_without_duplicate_or_changed_event(tmp_path, lost_ack):
    location = os.environ.get('SAFETY_PEER_ROOT')
    if not location:
        pytest.skip('Set SAFETY_PEER_ROOT to the pinned receiver checkout for two real applications')
    peer_root = Path(location).resolve()
    assert (peer_root/'backend/app/main.py').is_file()
    equipment_db, safety_db = tmp_path/'equipment.db', tmp_path/'safety.db'
    engine = create_engine('sqlite:///'+str(equipment_db))
    upgrade_database(engine)
    with Session(engine) as db:
        db.add(User(username='link-admin', role=UserRole.ADMIN, is_active=True, hashed_password='unused'))
        equipment = Equipment(code='EQ-BL-CONTRACT', name='联动测试锅炉', equipment_system=EquipmentSystem.BOILER,
                              criticality=Criticality.A, health_score=100)
        db.add(equipment)
        db.commit()
        equipment_id = equipment.id
    token = jwt.encode({'sub': 'link-admin', 'exp': int(time.time())+300}, KEY, algorithm='HS256')
    headers = {'Authorization': 'Bearer '+token}
    try:
        with application(peer_root, safety_db, tmp_path/'receiver.log') as receiver:
            with forwarding_peer(receiver, drop_first=lost_ack) as (proxy, calls):
                with application(ROOT, equipment_db, tmp_path/'sender-first.log', target=proxy) as sender:
                    response = httpx.post(sender+'/api/defects', headers=headers, json={
                        'equipment_id': equipment_id, 'title': '原始紧急事件', 'description': '原始源头数据',
                        'severity': 'CRITICAL'}, timeout=10)
                    assert response.status_code == 200, response.text
                    did = response.json()['data']['id']
                    expected = 'FAILED' if lost_ack else 'SYNCED'
                    assert response.json()['data']['safety_sync_status'] == expected
                peer_engine = create_engine('sqlite:///'+str(safety_db))
                try:
                    with peer_engine.connect() as conn:
                        assert conn.scalar(text('SELECT count(*) FROM hazards')) == 1
                        assert conn.scalar(text('SELECT count(*) FROM integration_receipts')) == 1
                    if lost_ack:
                        # 原进程退出，再改本地对象；重启只能发已保存的原事件。
                        with engine.begin() as conn:
                            conn.execute(text("UPDATE defects SET description='后来改动的内容' WHERE id=:id"), {'id': did})
                            conn.execute(text("UPDATE equipments SET name='后来改名设备' WHERE id=:id"), {'id': equipment_id})
                        with application(ROOT, equipment_db, tmp_path/'sender-restarted.log', target=proxy) as sender:
                            repeated = httpx.post(sender+f'/api/defects/{did}/safety-sync', headers=headers, timeout=10)
                            assert repeated.status_code == 200, repeated.text
                            with engine.connect() as conn:
                                assert conn.scalar(text('SELECT safety_sync_status FROM defects WHERE id=:id'), {'id': did}) == 'SYNCED'
                            assert len(calls) == 2 and calls[0] == calls[1]
                    with peer_engine.connect() as conn:
                        assert conn.scalar(text('SELECT count(*) FROM hazards')) == 1
                        assert conn.scalar(text('SELECT count(*) FROM integration_receipts')) == 1
                        assert '原始源头数据' in conn.scalar(text('SELECT description FROM hazards'))
                finally:
                    peer_engine.dispose()
    finally:
        engine.dispose()
