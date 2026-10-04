"""Real API snapshots, stale stocktakes and transaction boundaries on both databases."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
from threading import Event, Lock
from uuid import uuid4

import pytest
from sqlalchemy import event, text

from app.api.deps import create_access_token
from app.models.spare_part import SparePart, StockMovement
from .concurrency import post_concurrently
from .test_stock_transactions import stock_context, overlap_stock_reads  # noqa: F401


def snapshot(ctx, listing=False):
    path = '/api/spare-parts' if listing else f'/api/spare-parts/{ctx.part_id}'
    response = ctx.client.get(path)
    assert response.status_code == 200, response.text
    data = response.json()['data']
    return data['items'][0] if listing else data


def movement(ctx, kind, qty, **extra):
    return ctx.client.post(f'/api/spare-parts/{ctx.part_id}/movements',
                           json={'movement_type': kind, 'qty': qty, **extra})


def assert_stock(ctx, qty, rows):
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal(qty)
        assert db.query(StockMovement).filter_by(spare_part_id=ctx.part_id).count() == rows


@contextmanager
def pause_first(factory, name, matches):
    entered, release, mutex = Event(), Event(), Lock()
    seen = False

    def pause(session, *args):
        nonlocal seen
        if not matches(*args):
            return
        with mutex:
            if seen:
                return
            seen = True
        entered.set()
        assert release.wait(10), 'Paused real database event was not released'

    event.listen(factory, name, pause)
    try:
        yield entered, release
    finally:
        release.set()
        event.remove(factory, name, pause)


def test_all_part_responses_include_current_stock_revision(stock_context):
    ctx = stock_context
    assert snapshot(ctx)['stock_revision'] == snapshot(ctx, listing=True)['stock_revision'] == 0
    created = ctx.client.post('/api/spare-parts', json={'name': 'second bearing', 'stock_qty': 3})
    assert created.status_code == 200, created.text
    assert created.json()['data']['stock_revision'] == 0
    updated = ctx.client.put(f'/api/spare-parts/{ctx.part_id}', json={'name': 'renamed bearing'})
    assert updated.status_code == 200
    assert updated.json()['data']['stock_revision'] == 0
    assert_stock(ctx, '10', 0)


@pytest.mark.parametrize('revision', [-1, True, 0.0, '0', 2147483648])
def test_invalid_snapshot_revision_is_rejected_without_writes(stock_context, revision):
    ctx = stock_context
    response = movement(ctx, 'ADJUST', 0, expected_stock_revision=revision)
    assert response.status_code == 422, response.text
    assert_stock(ctx, '10', 0)


@pytest.mark.parametrize('extra', [{}, {'expected_stock_revision': None}])
def test_unguarded_legacy_stocktake_is_rejected(stock_context, extra):
    ctx = stock_context
    response = movement(ctx, 'ADJUST', 0, **extra)
    assert response.status_code == 409, response.text
    assert '更新客户端' in response.json()['detail']
    assert_stock(ctx, '10', 0)


@pytest.mark.parametrize(('operation', 'expected'), [('IN', '12'), ('OUT', '8'), ('receive', '12')])
def test_stale_stocktake_preserves_intervening_inventory(stock_context, operation, expected):
    ctx = stock_context
    # The fixture has no movements: its original snapshot revision is zero.
    if operation == 'receive':
        changed = ctx.client.post(f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive',
                                  json={'received_qty': 2})
    else:
        changed = movement(ctx, operation, 2)
    assert changed.status_code == 200, changed.text
    response = movement(ctx, 'ADJUST', 10, expected_stock_revision=0)
    assert response.status_code == 409, response.text
    assert '库存已有变动' in response.json()['detail']
    assert_stock(ctx, expected, 1)


def test_returning_to_the_same_quantity_does_not_restore_old_revision(stock_context):
    ctx = stock_context
    assert movement(ctx, 'IN', 2).status_code == 200
    assert movement(ctx, 'OUT', 2).status_code == 200
    assert_stock(ctx, '10', 2)
    assert movement(ctx, 'ADJUST', 9, expected_stock_revision=0).status_code == 409
    assert_stock(ctx, '10', 2)


def test_another_part_does_not_invalidate_this_stocktake(stock_context):
    ctx = stock_context
    created = ctx.client.post('/api/spare-parts', json={'name': 'unrelated', 'stock_qty': 3})
    assert created.status_code == 200
    other_id = created.json()['data']['id']
    assert ctx.client.post(f'/api/spare-parts/{other_id}/movements',
                           json={'movement_type': 'IN', 'qty': 1}).status_code == 200
    response = movement(ctx, 'ADJUST', 7, expected_stock_revision=0)
    assert response.status_code == 200, response.text
    assert_stock(ctx, '7', 1)
    assert snapshot(ctx)['stock_revision'] == response.json()['data']['movement']['id']


def test_same_quantity_stocktake_invalidates_duplicate_confirmation(stock_context):
    ctx = stock_context
    response = movement(ctx, 'ADJUST', 10, expected_stock_revision=0)
    assert response.status_code == 200, response.text
    revision = response.json()['data']['stock_revision']
    assert revision == response.json()['data']['movement']['id'] > 0
    assert snapshot(ctx)['stock_revision'] == revision
    assert movement(ctx, 'ADJUST', 10, expected_stock_revision=0).status_code == 409
    assert_stock(ctx, '10', 1)


def test_two_stocktakes_of_the_same_snapshot_book_only_one(stock_context):
    ctx = stock_context
    path = f'/api/spare-parts/{ctx.part_id}/movements'
    with overlap_stock_reads(ctx.engine):
        responses = post_concurrently(ctx, [
            (path, {'movement_type': 'ADJUST', 'qty': qty, 'expected_stock_revision': 0})
            for qty in (7, 8)])
    assert sorted(r.status_code for r in responses) == [200, 409], [r.text for r in responses]
    winner = next(r.json()['data'] for r in responses if r.status_code == 200)
    assert_stock(ctx, str(winner['stock_qty']), 1)
    assert winner['stock_revision'] == winner['movement']['id']


def test_waiting_stocktake_refreshes_revision_after_lock(stock_context):
    ctx = stock_context
    matches = lambda obj: isinstance(obj, SparePart) and obj.id == ctx.part_id
    with pause_first(ctx.factory, 'loaded_as_persistent', matches) as (entered, release):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(movement, ctx, 'ADJUST', 10, expected_stock_revision=0)
            try:
                assert entered.wait(10), 'Initial real part read was not reached'
                assert movement(ctx, 'IN', 2).status_code == 200
            finally:
                release.set()
            assert pending.result(timeout=15).status_code == 409
    assert_stock(ctx, '12', 1)


@pytest.mark.parametrize('listing', [False, True])
def test_stock_and_revision_are_read_from_one_snapshot(stock_context, listing):
    ctx = stock_context
    matches = lambda obj: isinstance(obj, SparePart) and obj.id == ctx.part_id
    with pause_first(ctx.factory, 'loaded_as_persistent', matches) as (entered, release):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(snapshot, ctx, listing)
            try:
                assert entered.wait(10)
                assert movement(ctx, 'IN', 2).status_code == 200
            finally:
                release.set()
            old = pending.result(timeout=15)
    assert Decimal(old['stock_qty']) == 10
    assert old['stock_revision'] == 0
    latest = snapshot(ctx)
    assert Decimal(latest['stock_qty']) == 12
    assert latest['stock_revision'] > 0
    assert movement(ctx, 'ADJUST', 10, expected_stock_revision=old['stock_revision']).status_code == 409
    assert_stock(ctx, '12', 1)


def test_ledger_failure_preserves_revision_for_retry(stock_context):
    ctx = stock_context
    if ctx.engine.dialect.name == 'postgresql':
        rejection = 'ALTER TABLE stock_movements ADD CONSTRAINT reject_stocktake CHECK (qty > 100)'
        cleanup = 'ALTER TABLE stock_movements DROP CONSTRAINT reject_stocktake'
    else:
        rejection = "CREATE TRIGGER reject_stocktake BEFORE INSERT ON stock_movements BEGIN SELECT RAISE(ABORT, 'test rejection'); END"
        cleanup = 'DROP TRIGGER reject_stocktake'
    with ctx.engine.begin() as conn:
        conn.execute(text(rejection))
    try:
        assert movement(ctx, 'ADJUST', 0, expected_stock_revision=0).status_code == 500
        assert_stock(ctx, '10', 0)
        assert snapshot(ctx)['stock_revision'] == 0
    finally:
        with ctx.engine.begin() as conn:
            conn.execute(text(cleanup))
    assert movement(ctx, 'ADJUST', 0, expected_stock_revision=0).status_code == 200
    assert_stock(ctx, '0', 1)


def test_success_response_keeps_its_snapshot_after_later_commit(stock_context):
    ctx = stock_context
    with pause_first(ctx.factory, 'after_commit', lambda: True) as (entered, release):
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(movement, ctx, 'OUT', 1)
            try:
                assert entered.wait(10), 'First movement did not commit'
                later = movement(ctx, 'IN', 2)
                assert later.status_code == 200
            finally:
                release.set()
            first = pending.result(timeout=15)
    assert first.status_code == 200
    data = first.json()['data']
    assert data['stock_qty'] == 9
    assert data['stock_revision'] == data['movement']['id']
    assert later.json()['data']['stock_qty'] == 11
    assert snapshot(ctx)['stock_revision'] == later.json()['data']['stock_revision'] > data['stock_revision']
    assert_stock(ctx, '11', 2)


def test_successful_receipt_replay_does_not_change_revision(stock_context):
    ctx = stock_context
    path = f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive'
    body = {'received_qty': 2, 'request_id': str(uuid4())}
    first = ctx.client.post(path, json=body)
    assert first.status_code == 200
    before = snapshot(ctx)['stock_revision']
    replay = ctx.client.post(path, json=body)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert snapshot(ctx)['stock_revision'] == before > 0
    assert_stock(ctx, '12', 1)


def test_snapshot_guards_preserve_role_and_missing_target_errors(stock_context):
    ctx = stock_context
    headers = {'Authorization': 'Bearer ' + create_access_token('stock-viewer')}
    assert ctx.client.post(f'/api/spare-parts/{ctx.part_id}/movements', headers=headers,
                           json={'movement_type': 'ADJUST', 'qty': 0, 'expected_stock_revision': 0}).status_code == 403
    assert ctx.client.post('/api/spare-parts/999999/movements',
                           json={'movement_type': 'ADJUST', 'qty': 0, 'expected_stock_revision': 0}).status_code == 404
    assert_stock(ctx, '10', 0)
