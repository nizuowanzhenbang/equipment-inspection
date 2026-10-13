"""采购数量、金额与事务内原子日序号。"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.models.purchase_request import PurchaseNumberSequence, PurchaseRequest, PRSource, PRStatus
from app.models.spare_part import SparePart
from app.schemas.spare_part import MAX_STOCK_QUANTITY
from app.utils.transactions import lock_spare_part

MAX_AMOUNT = Decimal('9999999999.99')
MAX_SEQUENCE = 2147483647


def estimated_amount(qty, price):
    price = Decimal(price or 0)
    if not price.is_finite() or not 0 <= price <= MAX_STOCK_QUANTITY:
        raise HTTPException(409, '备件单价不可用于采购，请先核对')
    amount = (Decimal(qty) * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if not 0 <= amount <= MAX_AMOUNT:
        raise HTTPException(409, '预估金额超出可表示范围，请核对采购数量和单价')
    return amount


def allocate_purchase_number(db):
    day = datetime.utcnow().strftime('%Y%m%d')
    prefix = f'PR-{day}-'
    if db.get(PurchaseNumberSequence, day) is None:
        # 初始化兼容旧数据，不能按条数回退或把异形编号当作序号。
        codes = db.query(PurchaseRequest.pr_no).filter(PurchaseRequest.pr_no.like(prefix+'%')).all()
        largest = max((int(code[len(prefix):]) for (code,) in codes
                       if code[len(prefix):].isascii() and code[len(prefix):].isdigit()), default=0)
        if largest >= MAX_SEQUENCE:
            raise HTTPException(409, '当日采购编号已达到上限')
        dialect = db.get_bind().dialect.name
        insert = sqlite_insert if dialect == 'sqlite' else pg_insert
        db.execute(insert(PurchaseNumberSequence).values(day=day, last_value=largest)
                   .on_conflict_do_nothing(index_elements=['day']))
    value = db.execute(update(PurchaseNumberSequence)
                       .where(PurchaseNumberSequence.day == day, PurchaseNumberSequence.last_value < MAX_SEQUENCE)
                       .values(last_value=PurchaseNumberSequence.last_value+1)
                       .returning(PurchaseNumberSequence.last_value)).scalar_one_or_none()
    if value is None:
        raise HTTPException(409, '当日采购编号已达到上限')
    return f'{prefix}{value:04d}'


def generate_low_stock(db, applicant):
    """锁定/刷新全部候选后生成，API 与调度器使用同一事务规则。"""
    ids = db.query(SparePart.id).filter(SparePart.stock_qty < SparePart.min_qty).order_by(SparePart.id).all()
    # 所有物料锁必须在编号锁之前取得，避免多物料批次与手工创建互等。
    parts = [lock_spare_part(db, part_id) for (part_id,) in ids]
    created, skipped = [], []
    active = (PRStatus.DRAFT, PRStatus.SUBMITTED, PRStatus.APPROVED, PRStatus.SENT)
    for part in parts:
        if part is None:
            continue
        stock, minimum = part.stock_qty or Decimal('0'), part.min_qty or Decimal('0')
        if stock >= minimum:
            continue
        if db.query(PurchaseRequest.id).filter(PurchaseRequest.spare_part_id == part.id,
                                               PurchaseRequest.status.in_(active)).first():
            continue
        suggested = max(2*minimum-stock, minimum)
        try:
            if not (0 <= stock <= MAX_STOCK_QUANTITY and 0 <= minimum <= MAX_STOCK_QUANTITY
                    and 0 < suggested <= MAX_STOCK_QUANTITY):
                raise HTTPException(409, '库存/建议数量超出可表示范围，请核对安全库存')
            amount = estimated_amount(suggested, part.unit_price)
        except HTTPException as exc:
            skipped.append({'spare_part_id': part.id, 'spare_part_code': part.code, 'reason': exc.detail})
            continue
        pr = PurchaseRequest(pr_no=allocate_purchase_number(db), spare_part_id=part.id,
                             qty=suggested, estimated_amount=amount,
                             urgency='URGENT' if stock <= 0 else 'NORMAL',
                             reason=f'低库存自动触发：当前 {stock}，安全 {minimum}',
                             source=PRSource.AUTO_LOW_STOCK, status=PRStatus.SUBMITTED,
                             applicant=applicant, submitted_at=datetime.utcnow())
        db.add(pr)
        db.flush()
        created.append({'pr_no': pr.pr_no, 'spare_part_code': part.code, 'qty': float(suggested)})
    return {'created': created, 'skipped': skipped}
