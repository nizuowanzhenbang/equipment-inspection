"""就绪状态和请求日志的外部行为回归。"""
import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app import main
from app.migrate import HEAD


@pytest.fixture
def readiness_db(monkeypatch):
    engine = create_engine('sqlite://', poolclass=StaticPool,
                           connect_args={'check_same_thread': False})
    monkeypatch.setattr(main, 'engine', engine)
    yield engine
    engine.dispose()


@pytest.mark.parametrize('versions', [None, [], ['old_revision'], [HEAD, 'unexpected']])
def test_not_ready_when_migration_missing_or_not_current(readiness_db, versions):
    if versions is not None:
        with readiness_db.begin() as connection:
            connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32))'))
            for version in versions:
                connection.execute(text('INSERT INTO alembic_version VALUES (:version)'),
                                   {'version': version})
    response = TestClient(main.app).get('/ready')
    assert response.status_code == 503
    assert response.json() == {'status': 'not_ready'}
    assert TestClient(main.app).get('/health').json()['status'] == 'ok'


def test_ready_when_database_is_at_head(readiness_db):
    with readiness_db.begin() as connection:
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32))'))
        connection.execute(text('INSERT INTO alembic_version VALUES (:version)'), {'version': HEAD})
    response = TestClient(main.app).get('/ready')
    assert response.status_code == 200
    assert response.json() == {'status': 'ready'}


def test_connection_failure_has_no_details(monkeypatch, caplog):
    class UnavailableDatabase:
        def connect(self):
            raise RuntimeError('postgresql://admin:private-password@internal-host/database')

    monkeypatch.setattr(main, 'engine', UnavailableDatabase())
    with caplog.at_level(logging.INFO):
        response = TestClient(main.app).get('/ready')
    assert response.status_code == 503
    assert response.json() == {'status': 'not_ready'}
    assert 'private-password' not in response.text + caplog.text
    assert 'internal-host' not in response.text + caplog.text


@pytest.mark.parametrize('incoming', [None, '', 'a' * 65, 'unsafe id', 'bad\r\nlog', 'bad/token'])
def test_invalid_or_absent_request_id_is_replaced(incoming):
    headers = {} if incoming is None else {'X-Request-ID': incoming}
    first = TestClient(main.app).get('/health', headers=headers)
    second = TestClient(main.app).get('/health', headers=headers)
    assert UUID(first.headers['X-Request-ID']).version == 4
    assert first.headers['X-Request-ID'] != second.headers['X-Request-ID']


def test_request_id_and_bounded_metadata_are_logged(caplog):
    with caplog.at_level(logging.INFO):
        response = TestClient(main.app).get('/health?token=secret-query', headers={
            'X-Request-ID': 'probe-01.abc_xyz', 'Authorization': 'Bearer secret-header'})
    assert response.headers['X-Request-ID'] == 'probe-01.abc_xyz'
    records = [record for record in caplog.records if hasattr(record, 'request_id')]
    assert len(records) == 1
    record = records[0]
    assert record.request_id == 'probe-01.abc_xyz'
    assert record.method == 'GET'
    assert record.path == '/health'
    assert record.status == 200
    assert record.duration_ms >= 0
    assert 'secret-query' not in record.getMessage()
    assert 'secret-header' not in record.getMessage()


def test_error_and_path_secrets_do_not_leak(caplog):
    from app.observability import RequestLoggingMiddleware

    isolated = FastAPI()
    isolated.add_middleware(RequestLoggingMiddleware)

    @isolated.post('/fail/{token}')
    def fail(token: str):
        raise RuntimeError('raw-exception-secret')

    with caplog.at_level(logging.INFO):
        response = TestClient(isolated, raise_server_exceptions=False).post(
            '/fail/path-secret?token=query-secret', json={'password': 'body-secret'})
        missing = TestClient(isolated).get('/unmatched-path-secret')
    assert response.status_code == 500
    assert UUID(response.headers['X-Request-ID']).version == 4
    records = [record for record in caplog.records if hasattr(record, 'request_id')]
    assert [record.path for record in records] == ['/fail/{token}', '<unmatched>']
    assert records[0].status == 500
    assert missing.status_code == 404
    output = response.text + '\n'.join(record.getMessage() for record in records)
    for secret in ['raw-exception-secret', 'path-secret', 'query-secret', 'body-secret']:
        assert secret not in output
    assert all(record.exc_info is None for record in records)


def test_duplicate_request_ids_are_replaced():
    response = TestClient(main.app).get('/health', headers=[
        ('X-Request-ID', 'first-id'), ('X-Request-ID', 'second-id')])
    assert UUID(response.headers['X-Request-ID']).version == 4


def test_stream_failure_keeps_id_and_redacts_exception(caplog):
    from starlette.responses import StreamingResponse

    from app.observability import RequestLoggingMiddleware

    isolated = FastAPI()
    isolated.add_middleware(RequestLoggingMiddleware)

    @isolated.get('/stream')
    def stream():
        async def chunks():
            yield b'first chunk'
            raise RuntimeError('stream-private-password')
        return StreamingResponse(chunks())

    with caplog.at_level(logging.INFO):
        response = TestClient(isolated, raise_server_exceptions=False).get('/stream')
    assert response.status_code == 200  # headers were already sent
    assert UUID(response.headers['X-Request-ID']).version == 4
    record = next(record for record in caplog.records if hasattr(record, 'request_id'))
    assert record.status == 500
    with pytest.raises(RuntimeError, match='Request failed after response started') as caught:
        TestClient(isolated).get('/stream')
    assert caught.value.__suppress_context__
    assert 'stream-private-password' not in caplog.text


@pytest.mark.parametrize('protocol', ['websockets', 'websockets-sansio'])
def test_real_uvicorn_websocket_handshakes_never_log_query_tokens(tmp_path, protocol):
    """捕获真实服务器输出，避免只测试过滤器却漏掉协议实现的日志。"""
    server_module = tmp_path / 'probe_ws_app.py'
    server_module.write_text('''
from fastapi import WebSocket
from app import main
app = main.app
async def websocket(ws: WebSocket):
    if ws.query_params.get('token') == 'accepted-query-secret':
        await ws.accept()
        await ws.close()
    else:
        await ws.close(code=4401)
main.ws_endpoint = websocket
''', encoding='utf-8')
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        port = reserved.getsockname()[1]
    environment = dict(os.environ)
    environment['PYTHONPATH'] = os.pathsep.join([
        str(tmp_path), str(Path(__file__).resolve().parents[1])])
    output_file = tmp_path / 'uvicorn.log'
    with output_file.open('w', encoding='utf-8') as output:
        process = subprocess.Popen([
            sys.executable, '-m', 'uvicorn', 'probe_ws_app:app', '--host', '127.0.0.1',
            '--port', str(port), '--lifespan', 'off', '--no-access-log',
            '--ws', protocol, '--log-level', 'debug'], env=environment,
            stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 15
            while True:
                assert process.poll() is None, output_file.read_text(encoding='utf-8')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        pytest.fail('Uvicorn startup timed out')
                    time.sleep(0.05)
            for token, expected in [('accepted-query-secret', b'101'),
                                    ('rejected-query-secret', b'403')]:
                with socket.create_connection(('127.0.0.1', port), timeout=3) as client:
                    client.sendall((f'GET /ws?token={token} HTTP/1.1\r\n'
                                    f'Host: 127.0.0.1:{port}\r\n'
                                    'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                                    'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n'
                                    'Sec-WebSocket-Version: 13\r\n\r\n').encode('ascii'))
                    assert expected in client.recv(4096).split(b'\r\n', 1)[0]
        finally:
            process.terminate()
            process.wait(timeout=10)
    logs = output_file.read_text(encoding='utf-8')
    assert 'Uvicorn running' in logs  # prove capture was active
    assert 'accepted-query-secret' not in logs
    assert 'rejected-query-secret' not in logs
    assert 'WebSocket handshake accepted' in logs
    assert 'WebSocket handshake rejected' in logs
