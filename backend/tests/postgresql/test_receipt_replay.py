"""Stable receipt identities protect real stock after a lost response."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.api.deps import create_access_token
from app.models.purchase_request import PurchaseRequest, PRStatus
from app.models.spare_part import SparePart, StockMovement
from app.models.user import User, UserRole
from .concurrency import post_concurrently
from .test_stock_transactions import stock_context, overlap_stock_reads  # noqa: F401


def receive(ctx, qty='2', request_id=None, purchase_id=None, **kwargs):
    body = {'received_qty': qty}
    if request_id is not None:
        body['request_id'] = request_id
    return ctx.client.post(f'/api/purchase-requests/{purchase_id or ctx.purchase_ids[0]}/receive',
                           json=body, **kwargs)


def assert_receipt(ctx, stock, received, movements, requests):
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal(stock)
        assert db.get(PurchaseRequest, ctx.purchase_ids[0]).received_qty == Decimal(received)
        assert db.query(StockMovement).count() == movements
        assert db.scalar(text('SELECT count(*) FROM purchase_receipts')) == requests


def test_partial_receipt_lost_response_reuses_result(stock_context):
    ctx, key = stock_context, str(uuid4())
    first = receive(ctx, '2.00', key)
    assert first.status_code == 200, first.text
    retry = receive(ctx, '2', key.upper())
    assert retry.status_code == 200, retry.text
    assert retry.json() == first.json()
    assert_receipt(ctx, '12', '2', 1, 1)


def test_completed_receipt_can_be_confirmed_again(stock_context):
    ctx, key = stock_context, str(uuid4())
    first = receive(ctx, '5', key)
    assert first.status_code == 200, first.text
    retry = receive(ctx, '5', key)
    assert retry.status_code == 200, retry.text
    assert retry.json() == first.json()
    assert first.json()['data']['status'] == 'RECEIVED'
    assert_receipt(ctx, '15', '5', 1, 1)


def test_replay_returns_first_snapshot_after_another_receipt(stock_context):
    ctx, key = stock_context, str(uuid4())
    first = receive(ctx, '2', key)
    later = receive(ctx, '1', str(uuid4()))
    assert first.status_code == later.status_code == 200
    retry = receive(ctx, '2', key)
    assert retry.status_code == 200, retry.text
    assert retry.json() == first.json()
    assert_receipt(ctx, '13', '3', 2, 2)


def test_successful_receipt_can_be_confirmed_after_cancellation(stock_context):
    ctx, key = stock_context, str(uuid4())
    first = receive(ctx, '2', key)
    assert first.status_code == 200
    assert ctx.client.post(f'/api/purchase-requests/{ctx.purchase_ids[0]}/cancel').status_code == 200
    retry = receive(ctx, '2', key)
    assert retry.status_code == 200, retry.text
    assert retry.json() == first.json()
    assert_receipt(ctx, '12', '2', 1, 1)
    with ctx.factory() as db:
        assert db.get(PurchaseRequest, ctx.purchase_ids[0]).status == PRStatus.CANCELLED


def test_changed_quantity_with_same_identity_conflicts(stock_context):
    ctx, key = stock_context, str(uuid4())
    assert receive(ctx, '2', key).status_code == 200
    response = receive(ctx, '3', key)
    assert response.status_code == 409, response.text
    assert_receipt(ctx, '12', '2', 1, 1)


def test_another_actor_cannot_reuse_receipt_identity(stock_context):
    ctx, key = stock_context, str(uuid4())
    assert receive(ctx, '2', key).status_code == 200
    with ctx.factory() as db:
        db.add(User(username='another-writer', role=UserRole.SUPERVISOR, hashed_password='unused'))
        db.commit()
    response = receive(ctx, '2', key, headers={
        'Authorization': 'Bearer ' + create_access_token('another-writer')})
    assert response.status_code == 409, response.text
    assert_receipt(ctx, '12', '2', 1, 1)


@pytest.mark.parametrize('conflicting', [False, True])
def test_overlapping_same_identity_receipts_commit_once(stock_context, conflicting):
    ctx, key = stock_context, str(uuid4())
    path = f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive'
    bodies = [{'received_qty': qty, 'request_id': key}
              for qty in ('2', '3' if conflicting else '2')]
    with overlap_stock_reads(ctx.engine):
        responses = post_concurrently(ctx, [(path, b) for b in bodies])
    assert sorted(r.status_code for r in responses) == [200, 409 if conflicting else 200], [r.text for r in responses]
    if not conflicting:
        assert responses[0].json() == responses[1].json()
    with ctx.factory() as db:
        purchase = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert purchase.received_qty in (Decimal('2'), Decimal('3'))
        assert db.get(SparePart, ctx.part_id).stock_qty == 10 + purchase.received_qty
        assert db.query(StockMovement).count() == 1
        assert db.scalar(text('SELECT count(*) FROM purchase_receipts')) == 1


def test_same_identity_is_scoped_to_purchase_order(stock_context):
    ctx, key = stock_context, str(uuid4())
    for pid in ctx.purchase_ids:
        assert receive(ctx, '2', key, purchase_id=pid).status_code == 200
    assert_receipt(ctx, '14', '2', 2, 2)


def test_legacy_unkeyed_receipts_keep_existing_semantics(stock_context):
    ctx = stock_context
    assert receive(ctx).status_code == receive(ctx).status_code == 200
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal('14')
        assert db.get(PurchaseRequest, ctx.purchase_ids[0]).received_qty == Decimal('4')
        assert db.query(StockMovement).count() == 2


@pytest.mark.parametrize('key', ['', 'not-a-uuid', 'x' * 100])
def test_invalid_identity_never_receives_stock(stock_context, key):
    ctx = stock_context
    response = receive(ctx, '2', key)
    assert response.status_code == 422, response.text
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal('10')
        assert db.query(StockMovement).count() == 0


def test_viewer_cannot_read_success_via_replay(stock_context):
    ctx, key = stock_context, str(uuid4())
    assert receive(ctx, '2', key).status_code == 200
    response = receive(ctx, '2', key, headers={
        'Authorization': 'Bearer ' + create_access_token('stock-viewer')})
    assert response.status_code == 403, response.text
    with ctx.factory() as db:
        assert db.query(StockMovement).count() == 1

@pytest.mark.parametrize('table', ['stock_movements', 'purchase_receipts'])
def test_failed_receipt_does_not_reserve_identity(stock_context, table):
    ctx, request_id = stock_context, str(uuid4())
    if ctx.engine.dialect.name == 'postgresql':
        rejection = f'ALTER TABLE {table} ADD CONSTRAINT reject_receipt_test CHECK (qty > 100)'
        cleanup = f'ALTER TABLE {table} DROP CONSTRAINT reject_receipt_test'
    else:
        rejection = f"CREATE TRIGGER reject_receipt_test BEFORE INSERT ON {table} BEGIN SELECT RAISE(ABORT, 'test rejection'); END"
        cleanup = 'DROP TRIGGER reject_receipt_test'
    with ctx.engine.begin() as conn:
        conn.execute(text(rejection))
    assert receive(ctx, '2', request_id).status_code == 500
    assert_receipt(ctx, '10', '0', 0, 0)
    with ctx.engine.begin() as conn:
        conn.execute(text(cleanup))
    assert receive(ctx, '2', request_id).status_code == 200
    assert_receipt(ctx, '12', '2', 1, 1)


def test_first_response_uses_committed_snapshot_when_later_receipt_wins_response_race(stock_context):
    from sqlalchemy import event
    ctx, key = stock_context, str(uuid4())
    later_results = []
    triggered = False

    def later_receipt(session):
        nonlocal triggered
        if triggered:
            return
        triggered = True
        later_results.append(receive(ctx, '1', str(uuid4())))

    event.listen(ctx.factory, 'after_commit', later_receipt)
    try:
        first = receive(ctx, '2', key)
    finally:
        event.remove(ctx.factory, 'after_commit', later_receipt)
    assert first.status_code == 200, first.text
    assert len(later_results) == 1 and later_results[0].status_code == 200
    assert first.json()['data']['stock_qty'] == 12
    assert receive(ctx, '2', key).json() == first.json()
    assert_receipt(ctx, '13', '3', 2, 2)
