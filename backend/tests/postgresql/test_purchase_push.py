"""Real HTTP peer and real database validate local push/receipt boundaries."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.models.audit import AuditLog
from app.models.purchase_request import PurchaseRequest, PRStatus
from .concurrency import post_request
from .purchase_http import procurement_server
from .test_purchase_states import action, assert_stock
from .test_stock_transactions import stock_context  # noqa: F401


def test_http_push_persists_payload_result_and_audit(stock_context, monkeypatch):
    ctx = stock_context
    with procurement_server(monkeypatch) as peer:
        response = post_request(ctx, action(ctx, 'send'))
    assert response.status_code == 200, response.text
    assert response.json()['data']['external_order_no'] == 'LOCAL-PO-1'
    assert len(peer.requests) == 1
    request = peer.requests[0]
    assert request['path'] == '/api/integration/material-requests'
    assert request['token'] == 'isolated-local-procurement-token'
    assert request['payload']['external_no'] == 'STOCK-PR-0'
    assert request['payload']['material_code'] == 'STOCK-TEST'
    assert request['payload']['qty'] == 5
    assert_stock(ctx, PRStatus.SENT)
    with ctx.factory() as db:
        pr = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert pr.sent_at is not None and pr.external_order_no == 'LOCAL-PO-1'
        audit = db.query(AuditLog).one()
        assert audit.action == 'pr.send' and audit.target_id == pr.id


@pytest.mark.parametrize('malformed', [False, True])
def test_http_failure_keeps_approval_and_releases_lock(stock_context, monkeypatch, malformed):
    ctx = stock_context
    with procurement_server(monkeypatch, status=200 if malformed else 503, malformed=malformed) as peer:
        response = post_request(ctx, action(ctx, 'send'))
        assert response.status_code == 400, response.text
        assert_stock(ctx, PRStatus.APPROVED)
        with ctx.factory() as db:
            pr = db.get(PurchaseRequest, ctx.purchase_ids[0])
            assert pr.sent_at is None and pr.external_order_no is None
            assert db.query(AuditLog).count() == 0
        peer.status, peer.malformed = 200, False
        retry = post_request(ctx, action(ctx, 'send'))
        assert retry.status_code == 200, retry.text
        assert len(peer.requests) == 2
    assert_stock(ctx, PRStatus.SENT)
    assert post_request(ctx, action(ctx, 'receive', {'received_qty': '5', 'request_id': str(uuid4())})).status_code == 200
    assert_stock(ctx, PRStatus.RECEIVED, '15', '5', 1, 1)


def test_http_send_then_waiting_final_receipt_keeps_completed_state(stock_context, monkeypatch):
    ctx, receipt_read = stock_context, Event()

    def loaded(session, instance):
        if isinstance(instance, PurchaseRequest) and instance.id == ctx.purchase_ids[0]:
            receipt_read.set()

    with procurement_server(monkeypatch, hold=True) as peer:
        with ThreadPoolExecutor(max_workers=2) as pool:
            sending = pool.submit(post_request, ctx, action(ctx, 'send'))
            assert peer.entered.wait(timeout=3)
            event.listen(ctx.factory, 'loaded_as_persistent', loaded)
            try:
                receiving = pool.submit(post_request, ctx, action(ctx, 'receive', {
                    'received_qty': '5', 'request_id': str(uuid4())}))
                assert receipt_read.wait(timeout=3), 'Receipt must read before attempting the held lock'
            finally:
                peer.release.set()
                event.remove(ctx.factory, 'loaded_as_persistent', loaded)
            sent, received = sending.result(timeout=10), receiving.result(timeout=10)
        assert sent.status_code == received.status_code == 200, [sent.text, received.text]
        assert len(peer.requests) == 1
    assert_stock(ctx, PRStatus.RECEIVED, '15', '5', 1, 1)
    assert post_request(ctx, action(ctx, 'send')).status_code == 400
    with ctx.factory() as db:
        assert db.query(AuditLog).count() == 1
        assert db.get(PurchaseRequest, ctx.purchase_ids[0]).external_order_no == 'LOCAL-PO-1'


def test_remote_success_is_not_rolled_back_when_local_audit_rejects(stock_context, monkeypatch):
    ctx = stock_context
    if ctx.engine.dialect.name == 'postgresql':
        rejection = 'ALTER TABLE audit_logs ADD CONSTRAINT reject_remote_audit CHECK (id < 0)'
    else:
        rejection = "CREATE TRIGGER reject_remote_audit BEFORE INSERT ON audit_logs BEGIN SELECT RAISE(ABORT, 'test rejection'); END"
    with ctx.engine.begin() as conn:
        conn.execute(text(rejection))
    with procurement_server(monkeypatch) as peer:
        response = post_request(ctx, action(ctx, 'send'))
    assert response.status_code == 500, response.text
    assert len(peer.requests) == 1  # HTTP peer succeeded; a local rollback cannot undo it.
    assert_stock(ctx, PRStatus.APPROVED)
    with ctx.factory() as db:
        pr = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert pr.sent_at is None and pr.external_order_no is None
        assert db.query(AuditLog).count() == 0
