"""Control real transaction ordering without replacing database results."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Event, Lock

from fastapi.testclient import TestClient
from sqlalchemy import event

from app.main import app


def post_request(context, request):
    path, body = request[:2]
    headers = request[2] if len(request) == 3 else context.headers
    client = TestClient(app, raise_server_exceptions=False, headers=headers)
    try:
        return client.post(path, json=body)
    finally:
        client.close()


def post_concurrently(context, requests):
    start = Barrier(len(requests))

    def submit(request):
        start.wait(timeout=10)
        return post_request(context, request)

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        return list(pool.map(submit, requests))


@contextmanager
def overlap_initial_reads(engine):
    """Both requests read the old state before attempting the shared write lock."""
    barrier = Barrier(2)
    seen = set()
    mutex = Lock()

    def after_read(connection, cursor, statement, parameters, context, executemany):
        sql = ' '.join(statement.lower().split())
        if not sql.startswith('select') or not any(part in sql for part in (
            'from defects left outer join equipments',
            'from inspection_points left outer join equipments',
            'from equipments where',
        )):
            return
        with mutex:
            if connection in seen or len(seen) >= 2:
                return
            seen.add(connection)
        barrier.wait(timeout=10)

    event.listen(engine, 'after_cursor_execute', after_read)
    try:
        yield
        assert len(seen) == 2, 'Both initial database reads must reach the concurrency barrier'
    finally:
        event.remove(engine, 'after_cursor_execute', after_read)


@contextmanager
def pause_next_read(engine, sql_fragment):
    """Pause one completed SELECT; another real transaction can commit meanwhile."""
    reached, release = Event(), Event()
    mutex = Lock()

    def after_read(connection, cursor, statement, parameters, context, executemany):
        sql = ' '.join(statement.lower().split())
        if not sql.startswith('select') or sql_fragment not in sql:
            return
        with mutex:
            if reached.is_set():
                return
            reached.set()
        if not release.wait(timeout=15):
            raise TimeoutError('Paused test transaction was not released')

    event.listen(engine, 'after_cursor_execute', after_read)
    try:
        yield reached, release
    finally:
        release.set()
        event.remove(engine, 'after_cursor_execute', after_read)
