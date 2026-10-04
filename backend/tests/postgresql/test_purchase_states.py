"""Real SQLite/PG API state ordering; pause after actual ORM rows are materialized."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
from threading import Barrier, Event, Lock
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.api.deps import create_access_token
from app.models.audit import AuditLog
from app.models.purchase_request import PurchaseRequest, PRStatus
from app.models.spare_part import SparePart, StockMovement
from .concurrency import post_request, post_concurrently
from .test_stock_transactions import stock_context  # noqa: F401


def action(ctx, name, body=None):
    return (f'/api/purchase-requests/{ctx.purchase_ids[0]}/{name}', body or {})


def set_status(ctx, status):
    with ctx.factory() as db:
        db.get(PurchaseRequest, ctx.purchase_ids[0]).status = status
        db.commit()


@contextmanager
def pause_purchase(ctx):
    reached, release = Event(), Event()
    mutex = Lock()

    def loaded(session, instance):
        if not isinstance(instance, PurchaseRequest) or instance.id != ctx.purchase_ids[0]:
            return
        with mutex:
            if reached.is_set():
                return
            reached.set()
        if not release.wait(timeout=15):
            raise TimeoutError('Purchase test reader was not released')

    event.listen(ctx.factory, 'loaded_as_persistent', loaded)
    try:
        yield reached, release
    finally:
        release.set()
        event.remove(ctx.factory, 'loaded_as_persistent', loaded)


def finish_while_first_read_is_paused(ctx, first, second):
    with pause_purchase(ctx) as (reached, release):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(post_request, ctx, first)
            try:
                assert reached.wait(timeout=10), 'First request must read the real purchase row'
                second_response = post_request(ctx, second)
            finally:
                release.set()
            first_response = pending.result(timeout=10)
    return first_response, second_response


@contextmanager
def overlap_purchase_reads(ctx):
    barrier, mutex, seen = Barrier(2), Lock(), set()

    def loaded(session, instance):
        if not isinstance(instance, PurchaseRequest) or instance.id != ctx.purchase_ids[0]:
            return
        with mutex:
            if session in seen or len(seen) >= 2:
                return
            seen.add(session)
        barrier.wait(timeout=10)

    event.listen(ctx.factory, 'loaded_as_persistent', loaded)
    try:
        yield
        assert len(seen) == 2, 'Both requests must materialize the original purchase state'
    finally:
        event.remove(ctx.factory, 'loaded_as_persistent', loaded)


def assert_stock(ctx, status, stock='10', received='0', movements=0, receipts=0):
    with ctx.factory() as db:
        pr = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert pr.status == status
        assert pr.received_qty == Decimal(received)
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal(stock)
        assert db.query(StockMovement).count() == movements
        assert db.scalar(text('SELECT count(*) FROM purchase_receipts')) == receipts


@pytest.mark.parametrize(('name', 'status', 'body'), [
    ('submit', PRStatus.DRAFT, {}),
    ('approve', PRStatus.SUBMITTED, {}),
    ('reject', PRStatus.SUBMITTED, {'reason': 'test rejection'}),
    ('send', PRStatus.APPROVED, {}),
])
def test_cancelled_order_cannot_be_revived_by_old_state(stock_context, name, status, body):
    ctx = stock_context
    set_status(ctx, status)
    stale, cancelled = finish_while_first_read_is_paused(ctx, action(ctx, name, body), action(ctx, 'cancel'))
    assert cancelled.status_code == 200, cancelled.text
    assert stale.status_code == 400, stale.text
    assert_stock(ctx, PRStatus.CANCELLED)
    with ctx.factory() as db:
        assert db.query(AuditLog).count() == 0


@pytest.mark.parametrize(('qty', 'cancel_status', 'final_status'), [
    ('5', 400, PRStatus.RECEIVED), ('2', 200, PRStatus.CANCELLED),
])
def test_cancel_refreshes_after_receipt_commits(stock_context, qty, cancel_status, final_status):
    ctx, key = stock_context, str(uuid4())
    body = {'received_qty': qty, 'request_id': key}
    cancelled, received = finish_while_first_read_is_paused(ctx, action(ctx, 'cancel'), action(ctx, 'receive', body))
    assert received.status_code == 200, received.text
    assert cancelled.status_code == cancel_status, cancelled.text
    assert_stock(ctx, final_status, str(10 + Decimal(qty)), qty, 1, 1)
    replay = post_request(ctx, action(ctx, 'receive', body))
    assert replay.status_code == 200 and replay.json() == received.json()
    assert_stock(ctx, final_status, str(10 + Decimal(qty)), qty, 1, 1)


def test_receipt_refreshes_after_cancel_commits(stock_context):
    ctx = stock_context
    received, cancelled = finish_while_first_read_is_paused(
        ctx, action(ctx, 'receive', {'received_qty': '5', 'request_id': str(uuid4())}), action(ctx, 'cancel'))
    assert cancelled.status_code == 200
    assert received.status_code == 400, received.text
    assert_stock(ctx, PRStatus.CANCELLED)


@pytest.mark.parametrize(('name', 'initial', 'final', 'audit_count'), [
    ('submit', PRStatus.DRAFT, PRStatus.SUBMITTED, 0),
    ('approve', PRStatus.SUBMITTED, PRStatus.APPROVED, 1),
    ('reject', PRStatus.SUBMITTED, PRStatus.REJECTED, 0),
    ('send', PRStatus.APPROVED, PRStatus.SENT, 1),
    ('cancel', PRStatus.APPROVED, PRStatus.CANCELLED, 0),
])
def test_overlapping_state_operation_obeys_current_eligibility(stock_context, name, initial, final, audit_count):
    ctx = stock_context
    set_status(ctx, initial)
    request = action(ctx, name, {'reason': 'test rejection'} if name == 'reject' else {})
    with overlap_purchase_reads(ctx):
        responses = post_concurrently(ctx, [request, request])
    assert sorted(r.status_code for r in responses) == [200, 400], [r.text for r in responses]
    assert_stock(ctx, final)
    with ctx.factory() as db:
        assert db.query(AuditLog).count() == audit_count


def test_approval_and_rejection_share_one_state_decision(stock_context):
    ctx = stock_context
    set_status(ctx, PRStatus.SUBMITTED)
    with overlap_purchase_reads(ctx):
        responses = post_concurrently(ctx, [action(ctx, 'approve'), action(ctx, 'reject', {'reason': 'test rejection'})])
    assert sorted(r.status_code for r in responses) == [200, 400], [r.text for r in responses]
    final = PRStatus.APPROVED if responses[0].status_code == 200 else PRStatus.REJECTED
    assert_stock(ctx, final)
    with ctx.factory() as db:
        pr = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert pr.approver == 'stock-admin'
        assert (pr.approved_at is not None) == (final == PRStatus.APPROVED)
        assert (pr.rejected_reason is not None) == (final == PRStatus.REJECTED)
        assert db.query(AuditLog).count() == (1 if final == PRStatus.APPROVED else 0)


def test_viewer_cannot_change_any_purchase_state(stock_context):
    ctx = stock_context
    headers = {'Authorization': 'Bearer ' + create_access_token('stock-viewer')}
    for name in ('submit', 'approve', 'reject', 'send', 'receive', 'cancel'):
        request = action(ctx, name, {'reason': 'no', 'received_qty': '5'}) + (headers,)
        assert post_request(ctx, request).status_code == 403
    assert_stock(ctx, PRStatus.APPROVED)


@pytest.mark.parametrize(('name', 'initial'), [('approve', PRStatus.SUBMITTED), ('send', PRStatus.APPROVED)])
def test_audit_failure_rolls_back_transition_and_metadata(stock_context, name, initial):
    ctx = stock_context
    set_status(ctx, initial)
    if ctx.engine.dialect.name == 'postgresql':
        reject = 'ALTER TABLE audit_logs ADD CONSTRAINT reject_purchase_audit CHECK (id < 0)'
        cleanup = 'ALTER TABLE audit_logs DROP CONSTRAINT reject_purchase_audit'
    else:
        reject = "CREATE TRIGGER reject_purchase_audit BEFORE INSERT ON audit_logs BEGIN SELECT RAISE(ABORT, 'test audit rejection'); END"
        cleanup = 'DROP TRIGGER reject_purchase_audit'
    with ctx.engine.begin() as conn:
        conn.execute(text(reject))
    response = post_request(ctx, action(ctx, name))
    assert response.status_code == 500, response.text
    assert_stock(ctx, initial)
    with ctx.factory() as db:
        pr = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert pr.approved_at is None and pr.sent_at is None
        assert pr.approver is None and pr.external_order_no is None
        assert db.query(AuditLog).count() == 0
    with ctx.engine.begin() as conn:
        conn.execute(text(cleanup))
    assert post_request(ctx, action(ctx, name)).status_code == 200
    assert_stock(ctx, PRStatus.APPROVED if name == 'approve' else PRStatus.SENT)
    with ctx.factory() as db:
        assert db.query(AuditLog).count() == 1


def test_missing_purchase_returns_404_without_business_changes(stock_context):
    ctx = stock_context
    for name in ('submit', 'approve', 'reject', 'send', 'receive', 'cancel'):
        response = ctx.client.post(f'/api/purchase-requests/99999999/{name}',
                                   json={'reason': 'no', 'received_qty': '5'})
        assert response.status_code == 404, response.text
    assert_stock(ctx, PRStatus.APPROVED)
