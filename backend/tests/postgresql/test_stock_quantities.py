"""Invalid inventory inputs never alter real stock, receipts or ledger rows."""
from decimal import Decimal

import pytest

from app.models.purchase_request import PurchaseRequest, PRStatus
from app.models.spare_part import SparePart, StockMovement, StockMovementType
from .test_stock_transactions import stock_context  # noqa: F401


INVALID_QUANTITIES = ['-0.01', '0.001', '100000000', 'NaN', 'Infinity',
                      '1.00000000000000000000000000001']


def assert_unchanged(ctx):
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal('10')
        assert db.query(StockMovement).count() == 0
        purchase = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert purchase.received_qty == 0
        assert purchase.status == PRStatus.APPROVED


@pytest.mark.parametrize('field', ['stock_qty', 'min_qty', 'unit_price'])
@pytest.mark.parametrize('value', INVALID_QUANTITIES)
def test_invalid_registration_is_rejected_before_persistence(stock_context, field, value):
    ctx = stock_context
    response = ctx.client.post('/api/spare-parts', json={'name': 'invalid', field: value})
    assert response.status_code == 422, response.text
    with ctx.factory() as db:
        assert db.query(SparePart).count() == 1
    assert_unchanged(ctx)


@pytest.mark.parametrize('field', ['min_qty', 'unit_price'])
@pytest.mark.parametrize('value', INVALID_QUANTITIES + [None])
def test_invalid_update_preserves_existing_values(stock_context, field, value):
    ctx = stock_context
    response = ctx.client.put(f'/api/spare-parts/{ctx.part_id}', json={field: value})
    assert response.status_code == 422, response.text
    with ctx.factory() as db:
        part = db.get(SparePart, ctx.part_id)
        assert part.min_qty == Decimal('1')
        assert part.unit_price == Decimal('2')
    assert_unchanged(ctx)


@pytest.mark.parametrize('movement', ['IN', 'OUT', 'ADJUST'])
@pytest.mark.parametrize('value', INVALID_QUANTITIES)
def test_invalid_movement_preserves_stock_and_ledger(stock_context, movement, value):
    ctx = stock_context
    response = ctx.client.post(f'/api/spare-parts/{ctx.part_id}/movements',
                               json={'movement_type': movement, 'qty': value})
    assert response.status_code == 422, response.text
    assert_unchanged(ctx)


@pytest.mark.parametrize('value', INVALID_QUANTITIES)
def test_invalid_receipt_preserves_purchase_and_stock(stock_context, value):
    ctx = stock_context
    response = ctx.client.post(f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive',
                               json={'received_qty': value})
    assert response.status_code == 422, response.text
    assert_unchanged(ctx)


def test_zero_stocktake_is_recorded_and_triggers_low_stock(stock_context):
    ctx = stock_context
    response = ctx.client.post(f'/api/spare-parts/{ctx.part_id}/movements',
                               json={'movement_type': 'ADJUST', 'qty': 0})
    assert response.status_code == 200, response.text
    assert response.json()['data']['stock_qty'] == 0
    assert response.json()['data']['low_stock'] is True
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == 0
        movement = db.query(StockMovement).one()
        assert movement.movement_type == StockMovementType.ADJUST
        assert movement.qty == 0


@pytest.mark.parametrize('operation', ['IN', 'OUT', 'receive'])
def test_zero_transfer_still_rejected(stock_context, operation):
    ctx = stock_context
    if operation == 'receive':
        path = f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive'
        body = {'received_qty': 0}
    else:
        path = f'/api/spare-parts/{ctx.part_id}/movements'
        body = {'movement_type': operation, 'qty': 0}
    response = ctx.client.post(path, json=body)
    assert response.status_code == 400, response.text
    assert_unchanged(ctx)


@pytest.mark.parametrize('operation', ['IN', 'receive'])
def test_stock_capacity_rejection_rolls_back_every_effect(stock_context, operation):
    ctx = stock_context
    maximum = Decimal('99999999.99')
    with ctx.factory() as db:
        db.get(SparePart, ctx.part_id).stock_qty = maximum
        db.commit()
    if operation == 'receive':
        path = f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive'
        body = {'received_qty': '0.01'}
    else:
        path = f'/api/spare-parts/{ctx.part_id}/movements'
        body = {'movement_type': 'IN', 'qty': '0.01'}
    response = ctx.client.post(path, json=body)
    assert response.status_code == 400, response.text
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == maximum
        assert db.query(StockMovement).count() == 0
        purchase = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert purchase.received_qty == 0
        assert purchase.status == PRStatus.APPROVED


def test_receipt_total_capacity_preserves_stock_and_order(stock_context):
    ctx = stock_context
    maximum = Decimal('99999999.99')
    with ctx.factory() as db:
        purchase = db.get(PurchaseRequest, ctx.purchase_ids[0])
        purchase.qty = maximum
        purchase.received_qty = maximum
        db.commit()
    response = ctx.client.post(f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive',
                               json={'received_qty': '0.01'})
    assert response.status_code == 400, response.text
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal('10')
        assert db.query(StockMovement).count() == 0
        purchase = db.get(PurchaseRequest, ctx.purchase_ids[0])
        assert purchase.received_qty == maximum
        assert purchase.status == PRStatus.APPROVED


def test_valid_decimal_boundaries_and_partial_update_remain_supported(stock_context):
    ctx = stock_context
    response = ctx.client.post('/api/spare-parts', json={
        'name': 'maximum bearing', 'stock_qty': '99999999.99',
        'min_qty': 0, 'unit_price': '1.2300',
    })
    assert response.status_code == 200, response.text
    assert Decimal(response.json()['data']['stock_qty']) == Decimal('99999999.99')
    response = ctx.client.put(f'/api/spare-parts/{ctx.part_id}', json={'notes': 'unchanged quantities'})
    assert response.status_code == 200, response.text
    response = ctx.client.post(f'/api/purchase-requests/{ctx.purchase_ids[0]}/receive',
                               json={'received_qty': '0.01'})
    assert response.status_code == 200, response.text
    response = ctx.client.post(f'/api/spare-parts/{ctx.part_id}/movements',
                               json={'movement_type': 'OUT', 'qty': '0.01'})
    assert response.status_code == 200, response.text
    with ctx.factory() as db:
        assert db.get(SparePart, ctx.part_id).stock_qty == Decimal('10')
        assert db.get(PurchaseRequest, ctx.purchase_ids[0]).received_qty == Decimal('0.01')
        assert [m.qty for m in db.query(StockMovement).order_by(StockMovement.id)] == [Decimal('0.01')] * 2
