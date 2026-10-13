"""真实 API/两个数据库验证新建、编号、补货与订单数量边界。"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from threading import Barrier, Lock
from uuid import uuid4

import pytest
from sqlalchemy import event, select

from app import scheduler
from app.database import Base
from app.models.purchase_request import PurchaseRequest, PRStatus
from app.models.spare_part import SparePart, StockMovement
from .test_stock_transactions import stock_context  # noqa: F401
from .concurrency import post_concurrently


def state(ctx):
    with ctx.engine.connect() as conn:
        return {table.name: [tuple(row) for row in conn.execute(select(table).order_by(*table.primary_key))]
                for table in Base.metadata.sorted_tables}


def create(ctx, **values):
    return ctx.client.post('/api/purchase-requests', json={'spare_part_id': ctx.part_id, 'qty': '1', **values})


@pytest.mark.parametrize('qty', ['0', '-1', '0.001', '1.2340000000000000001',
                                 '100000000', 'NaN', 'Infinity', '1e309', 10**400])
def test_invalid_create_quantity_is_422_and_changes_nothing(stock_context, qty):
    ctx = stock_context
    before = state(ctx)
    response = create(ctx, qty=qty)
    assert response.status_code == 422, response.text
    assert state(ctx) == before


def test_raw_exponent_overflow_has_serializable_422(stock_context):
    ctx = stock_context
    before = state(ctx)
    response = ctx.client.post('/api/purchase-requests', content=
                               '{"spare_part_id":'+str(ctx.part_id)+',"qty":1e309}',
                               headers={'Content-Type': 'application/json'})
    assert response.status_code == 422, response.text
    assert state(ctx) == before


@pytest.mark.parametrize('urgency', ['', 'IMMEDIATE'])
def test_unknown_urgency_is_rejected_before_writing(stock_context, urgency):
    before = state(stock_context)
    response = create(stock_context, urgency=urgency)
    assert response.status_code == 422, response.text
    assert state(stock_context) == before


@pytest.mark.parametrize('qty,price,amount', [('0.15', '0.30', '0.05'),
                                           ('1.20', '2.50', '3.00'),
                                           ('100', '99999999.99', '9999999999.00')])
def test_estimate_is_exact_half_up_and_within_numeric_capacity(stock_context, qty, price, amount):
    ctx = stock_context
    with ctx.factory() as db:
        db.get(SparePart, ctx.part_id).unit_price = Decimal(price)
        db.commit()
    response = create(ctx, qty=qty, urgency='URGENT')
    assert response.status_code == 200, response.text
    with ctx.factory() as db:
        record = db.get(PurchaseRequest, response.json()['data']['id'])
        assert record.qty == Decimal(qty)
        assert record.estimated_amount == Decimal(amount)


@pytest.mark.parametrize('price,qty', [('10000', '1000000'), ('-1', '1')])
def test_unrepresentable_amount_or_legacy_price_is_atomic_conflict(stock_context, price, qty):
    ctx = stock_context
    with ctx.factory() as db:
        db.get(SparePart, ctx.part_id).unit_price = Decimal(price)
        db.commit()
    before = state(ctx)
    response = create(ctx, qty=qty)
    assert response.status_code == 409, response.text
    assert state(ctx) == before


def test_deleted_purchase_does_not_reuse_any_allocated_number(stock_context):
    ctx = stock_context
    first, second = create(ctx), create(ctx)
    assert first.status_code == second.status_code == 200
    numbers = [first.json()['data']['pr_no'], second.json()['data']['pr_no']]
    with ctx.factory() as db:
        db.delete(db.get(PurchaseRequest, second.json()['data']['id']))
        db.commit()
    third = create(ctx)
    assert third.status_code == 200, third.text
    assert third.json()['data']['pr_no'] not in numbers


def test_legacy_maximum_is_respected_and_malformed_suffix_ignored(stock_context):
    ctx = stock_context
    prefix = datetime.utcnow().strftime('PR-%Y%m%d-')
    with ctx.factory() as db:
        for suffix in ['9003', '²']:
            db.add(PurchaseRequest(pr_no=prefix+suffix, spare_part_id=ctx.part_id, qty=1))
        db.commit()
    response = create(ctx)
    assert response.status_code == 200, response.text
    assert int(response.json()['data']['pr_no'][len(prefix):]) > 9003


@contextmanager
def expose_unlocked_legacy_reads(engine, kind):
    """只暂停真实旧的未加锁检查，不替换查询结果或当前锁实现。"""
    barrier, mutex, seen, locked = Barrier(2), Lock(), set(), set()
    def before(conn, cursor, statement, params, context, many):
        if ' '.join(statement.lower().split()).startswith('update spare_parts '):
            locked.add(conn)
    def after(conn, cursor, statement, params, context, many):
        sql = ' '.join(statement.lower().split())
        match = ('count(purchase_requests.id)' in sql if kind == 'number'
                 else sql.startswith('select') and 'from purchase_requests' in sql)
        if not match or conn in locked:
            return
        with mutex:
            if conn in seen or len(seen) >= 2:
                return
            seen.add(conn)
        barrier.wait(timeout=10)
    event.listen(engine, 'before_cursor_execute', before)
    event.listen(engine, 'after_cursor_execute', after)
    try:
        yield
    finally:
        event.remove(engine, 'before_cursor_execute', before)
        event.remove(engine, 'after_cursor_execute', after)


def test_different_parts_concurrently_get_distinct_numbers(stock_context):
    ctx = stock_context
    with ctx.factory() as db:
        other = SparePart(code='OTHER-PART', name='other', stock_qty=0, min_qty=1, unit_price=1)
        db.add(other); db.commit(); other_id = other.id
    with expose_unlocked_legacy_reads(ctx.engine, 'number'):
        responses = post_concurrently(ctx, [('/api/purchase-requests', {'spare_part_id': part, 'qty': 1}, ctx.headers)
                                           for part in [ctx.part_id, other_id]])
    assert [r.status_code for r in responses] == [200, 200], [r.text for r in responses]
    assert len({r.json()['data']['pr_no'] for r in responses}) == 2


def low_stock(ctx, **values):
    with ctx.factory() as db:
        db.query(PurchaseRequest).update({PurchaseRequest.status: PRStatus.CANCELLED})
        part = db.get(SparePart, ctx.part_id)
        for key, value in {'stock_qty': '0.15', 'min_qty': '0.30', 'unit_price': '0.10', **values}.items():
            setattr(part, key, Decimal(value))
        db.commit()


def test_auto_and_scheduler_race_create_one_exact_proposal(stock_context, monkeypatch):
    ctx = stock_context
    low_stock(ctx)
    monkeypatch.setattr(scheduler, 'SessionLocal', ctx.factory)
    start = Barrier(2)
    def api_call():
        start.wait(timeout=10)
        response = ctx.client.post('/api/purchase-requests/auto-generate')
        assert response.status_code == 200, response.text
    def scheduled():
        start.wait(timeout=10)
        return scheduler.auto_generate_purchase_requests()
    with expose_unlocked_legacy_reads(ctx.engine, 'proposal'), ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(api_call), pool.submit(scheduled)]
        for job in jobs:
            result = job.result(timeout=20)
            if isinstance(result, dict):
                assert 'error' not in result, result
    with ctx.factory() as db:
        records = db.query(PurchaseRequest).filter(PurchaseRequest.status == PRStatus.SUBMITTED).all()
        assert len(records) == 1
        assert records[0].qty == Decimal('0.45')
        assert records[0].estimated_amount == Decimal('0.05')
    again = ctx.client.post('/api/purchase-requests/auto-generate')
    assert again.status_code == 200 and again.json()['data']['created'] == []


@pytest.mark.parametrize('values', [{'min_qty': '99999999.99', 'stock_qty': '0'},
                                   {'min_qty': '1000000', 'stock_qty': '0', 'unit_price': '10000'}])
def test_auto_skips_overflow_but_generates_other_valid_part(stock_context, values):
    ctx = stock_context
    low_stock(ctx, **values)
    with ctx.factory() as db:
        part = SparePart(code='VALID-PART', name='valid', stock_qty=0, min_qty=1, unit_price=1)
        db.add(part); db.commit()
    response = ctx.client.post('/api/purchase-requests/auto-generate')
    assert response.status_code == 200, response.text
    body = response.json()['data']
    assert len(body['created']) == len(body['skipped']) == 1
    assert body['created'][0]['spare_part_code'] == 'VALID-PART'
    assert body['skipped'][0]['spare_part_code'] == 'STOCK-TEST'
    with ctx.factory() as db:
        assert db.query(PurchaseRequest).filter(PurchaseRequest.status == PRStatus.SUBMITTED).count() == 1


def test_over_receipt_rejected_before_stock_or_identity_write(stock_context):
    ctx = stock_context
    before = state(ctx)
    response = ctx.client.post(f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive',
                               json={'received_qty': '5.01', 'request_id': str(uuid4())})
    assert response.status_code == 409, response.text
    assert state(ctx) == before


def test_last_quantity_race_and_original_identity_replay(stock_context):
    ctx = stock_context
    path = f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive'
    payloads = [{'received_qty': '3', 'request_id': str(uuid4())} for _ in range(2)]
    responses = post_concurrently(ctx, [(path, body, ctx.headers) for body in payloads])
    assert sorted(r.status_code for r in responses) == [200, 409]
    winner = next(i for i, r in enumerate(responses) if r.status_code == 200)
    # 合法剩余到货完成后，旧身份仍返回原结果，不能按当前余量拒绝。
    final = ctx.client.post(path, json={'received_qty': '2', 'request_id': str(uuid4())})
    assert final.status_code == 200, final.text
    replay = ctx.client.post(path, json=payloads[winner])
    assert replay.status_code == 200 and replay.json() == responses[winner].json()
    with ctx.factory() as db:
        assert db.get(PurchaseRequest, ctx.purchase_ids[0]).received_qty == Decimal('5')
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal('15')
        assert db.query(StockMovement).count() == 2
