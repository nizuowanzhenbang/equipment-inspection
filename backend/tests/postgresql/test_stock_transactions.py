"""Real API inventory effects; SQLite and PostgreSQL keep isolated databases."""
from contextlib import contextmanager
from decimal import Decimal
from threading import Barrier, Lock
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.api.deps import create_access_token, get_db
from app.config import settings
from app.database import Base
from app.main import app
from app.models.purchase_request import PurchaseRequest, PRStatus
from app.models.spare_part import SparePart, StockMovement
from app.models.user import User, UserRole
from .concurrency import post_concurrently


@pytest.fixture(params=['sqlite', 'postgresql'])
def stock_context(request, tmp_path, monkeypatch):
    if request.param == 'postgresql':
        engine = request.getfixturevalue('pg_engine')
    else:
        engine = create_engine(f'sqlite:///{tmp_path / "stock.db"}',
                               connect_args={'check_same_thread': False})
        Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(settings, 'SAFETY_SYSTEM_URL', '')
    monkeypatch.setattr(settings, 'PROCUREMENT_SYSTEM_URL', '')
    with factory() as db:
        db.add_all([User(username=name, role=role, hashed_password='unused-token-test')
                    for name, role in [('stock-admin', UserRole.ADMIN),
                                       ('stock-viewer', UserRole.VIEWER)]])
        part = SparePart(code='STOCK-TEST', name='test bearing', stock_qty=Decimal('10'),
                         min_qty=Decimal('1'), unit_price=Decimal('2'))
        db.add(part)
        db.flush()
        purchases = [PurchaseRequest(pr_no=f'STOCK-PR-{i}', spare_part_id=part.id,
                                     qty=Decimal('5'), status=PRStatus.APPROVED)
                     for i in range(2)]
        db.add_all(purchases)
        db.commit()
        ctx = SimpleNamespace(engine=engine, factory=factory, part_id=part.id,
                              purchase_ids=[p.id for p in purchases],
                              headers={'Authorization': 'Bearer ' + create_access_token('stock-admin')})

    def sessions():
        with factory() as db:
            yield db

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = sessions
    ctx.client = TestClient(app, headers=ctx.headers, raise_server_exceptions=False)
    try:
        yield ctx
    finally:
        ctx.client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        if request.param == 'sqlite':
            engine.dispose()


@contextmanager
def overlap_stock_reads(engine):
    """Pause real completed initial reads, never replace query results or locks."""
    barrier, mutex, seen = Barrier(2), Lock(), set()

    def after_read(connection, cursor, statement, parameters, context, executemany):
        sql = ' '.join(statement.lower().split())
        if not sql.startswith('select') or not any(fragment in sql for fragment in (
                'from spare_parts where', 'from purchase_requests left outer join spare_parts')):
            return
        with mutex:
            if connection in seen or len(seen) >= 2:
                return
            seen.add(connection)
        barrier.wait(timeout=10)

    event.listen(engine, 'after_cursor_execute', after_read)
    try:
        yield
        assert len(seen) == 2, 'Both old-stock reads must reach the barrier'
    finally:
        event.remove(engine, 'after_cursor_execute', after_read)


@pytest.mark.parametrize(('movement', 'qty', 'statuses', 'expected', 'count'), [
    ('OUT', '7', [200, 400], '3', 1),
    ('OUT', '3', [200, 200], '4', 2),
    ('IN', '3', [200, 200], '16', 2),
])
def test_concurrent_movements_preserve_stock_and_ledger(stock_context, movement, qty,
                                                       statuses, expected, count):
    ctx = stock_context
    path = f'/api/spare-parts/{ctx.part_id}/movements'
    body = {'movement_type': movement, 'qty': qty}
    with overlap_stock_reads(ctx.engine):
        responses = post_concurrently(ctx, [(path, body), (path, body)])
    assert sorted(r.status_code for r in responses) == statuses, [r.text for r in responses]
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal(expected)
        rows = db.query(StockMovement).all()
        assert len(rows) == count
        assert all(m.qty == Decimal(qty) and m.operator == 'stock-admin' for m in rows)


def test_receipt_and_withdrawal_preserve_both_effects(stock_context):
    ctx = stock_context
    requests = [
        (f'/api/spare-parts/{ctx.part_id}/movements', {'movement_type': 'OUT', 'qty': '4'}),
        (f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive', {'received_qty': 2}),
    ]
    with overlap_stock_reads(ctx.engine):
        responses = post_concurrently(ctx, requests)
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal('8')
        assert db.query(StockMovement).count() == 2
        purchase = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert purchase.received_qty == Decimal('2')
        assert purchase.status == PRStatus.APPROVED


def test_two_purchases_preserve_all_receipts(stock_context):
    ctx = stock_context
    with overlap_stock_reads(ctx.engine):
        responses = post_concurrently(ctx, [
            (f'/api/purchase-requests/{pid}/receive', {'received_qty': 2})
            for pid in ctx.purchase_ids])
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal('14')
        assert db.query(StockMovement).count() == 2
        assert all(db.get(PurchaseRequest, pid).received_qty == Decimal('2')
                   for pid in ctx.purchase_ids)


def test_concurrent_final_receipt_is_not_booked_twice(stock_context):
    ctx = stock_context
    request = (f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive', {'received_qty': 5})
    with overlap_stock_reads(ctx.engine):
        responses = post_concurrently(ctx, [request, request])
    assert sorted(r.status_code for r in responses) == [200, 400], [r.text for r in responses]
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal('15')
        assert db.query(StockMovement).count() == 1
        purchase = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert purchase.status == PRStatus.RECEIVED
        assert purchase.received_qty == Decimal('5')


@pytest.mark.parametrize('receipt', [False, True])
def test_ledger_failure_rolls_back_stock_and_purchase(stock_context, receipt):
    ctx = stock_context
    # A real ledger constraint failure must undo all preceding database changes.
    if ctx.engine.dialect.name == 'postgresql':
        rejection = 'ALTER TABLE stock_movements ADD CONSTRAINT reject_test_stock CHECK (qty > 100)'
        cleanup = 'ALTER TABLE stock_movements DROP CONSTRAINT reject_test_stock'
    else:
        rejection = "CREATE TRIGGER reject_test_stock BEFORE INSERT ON stock_movements BEGIN SELECT RAISE(ABORT, 'test rejection'); END"
        cleanup = 'DROP TRIGGER reject_test_stock'
    with ctx.engine.begin() as conn:
        conn.execute(text(rejection))
    path, body = ((f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive', {'received_qty': 5})
                  if receipt else (f'/api/spare-parts/{ctx.part_id}/movements',
                                   {'movement_type': 'OUT', 'qty': '4'}))
    assert ctx.client.post(path, json=body).status_code == 500
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal('10')
        assert db.query(StockMovement).count() == 0
        purchase = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert purchase.status == PRStatus.APPROVED
        assert purchase.received_qty == 0
        assert purchase.received_at is None
    with ctx.engine.begin() as conn:
        conn.execute(text(cleanup))
    assert ctx.client.post(path, json=body).status_code == 200


def test_viewer_cannot_change_inventory(stock_context):
    ctx = stock_context
    headers = {'Authorization': 'Bearer ' + create_access_token('stock-viewer')}
    for path, body in [
        (f'/api/spare-parts/{ctx.part_id}/movements', {'movement_type': 'OUT', 'qty': '1'}),
        (f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive', {'received_qty': 1}),
    ]:
        assert ctx.client.post(path, json=body, headers=headers).status_code == 403
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal('10')
        assert db.query(StockMovement).count() == 0
