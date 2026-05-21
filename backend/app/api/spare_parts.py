"""备品备件 + 出入库 API"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_current_user, require_write, require_repairman
from app.models.defect import Defect
from app.models.spare_part import SparePart, StockMovement, StockMovementType
from app.models.ticket import WorkTicket
from app.models.user import User
from app.schemas.spare_part import (
    SparePartCreate, SparePartUpdate, SparePartResponse,
    MovementCreate, MovementResponse,
)
from app.utils.helpers import api_response, paginate_response, generate_spare_part_code

router = APIRouter(prefix="/api/spare-parts", tags=["备品备件"])


def _part_to_dict(p: SparePart) -> dict:
    data = SparePartResponse.model_validate(p).model_dump(mode="json")
    data["low_stock"] = float(p.stock_qty or 0) < float(p.min_qty or 0)
    return data


def _mv_to_dict(m: StockMovement) -> dict:
    data = MovementResponse.model_validate(m).model_dump(mode="json")
    if m.spare_part:
        data["spare_part_code"] = m.spare_part.code
        data["spare_part_name"] = m.spare_part.name
    return data


@router.get("")
def list_parts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
    category: Optional[str] = None,
    low_only: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(SparePart)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter((SparePart.name.like(like)) | (SparePart.code.like(like)) | (SparePart.spec.like(like)))
    if category:
        q = q.filter(SparePart.category == category)
    if low_only:
        q = q.filter(SparePart.stock_qty < SparePart.min_qty)
    total = q.count()
    rows = q.order_by(SparePart.code).offset((page - 1) * page_size).limit(page_size).all()
    return api_response(data=paginate_response([_part_to_dict(p) for p in rows], total, page, page_size))


@router.post("")
def create_part(payload: SparePartCreate, db: Session = Depends(get_db), _: User = Depends(require_write)):
    next_seq = (db.query(func.count(SparePart.id)).scalar() or 0) + 1
    p = SparePart(
        code=generate_spare_part_code(next_seq),
        **payload.model_dump(),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return api_response(message="物料已登记", data=_part_to_dict(p))


@router.get("/categories")
def list_categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.query(SparePart.category, func.count(SparePart.id)).group_by(SparePart.category).all()
    return api_response(data=[{"category": c or "未分类", "count": n} for c, n in rows])


@router.get("/{pid}")
def get_part(pid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    p = db.query(SparePart).filter(SparePart.id == pid).first()
    if not p:
        raise HTTPException(404, "物料不存在")
    return api_response(data=_part_to_dict(p))


@router.put("/{pid}")
def update_part(pid: int, payload: SparePartUpdate, db: Session = Depends(get_db), _: User = Depends(require_write)):
    p = db.query(SparePart).filter(SparePart.id == pid).first()
    if not p:
        raise HTTPException(404, "物料不存在")
    for f, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, f, v)
    db.commit()
    db.refresh(p)
    return api_response(message="已更新", data=_part_to_dict(p))


@router.post("/{pid}/movements")
def create_movement(
    pid: int, payload: MovementCreate,
    db: Session = Depends(get_db), current: User = Depends(require_repairman),
):
    p = db.query(SparePart).filter(SparePart.id == pid).first()
    if not p:
        raise HTTPException(404, "物料不存在")
    if payload.qty <= 0:
        raise HTTPException(400, "数量必须为正")
    if payload.defect_id and not db.query(Defect).filter(Defect.id == payload.defect_id).first():
        raise HTTPException(404, "关联缺陷不存在")
    if payload.work_ticket_id and not db.query(WorkTicket).filter(WorkTicket.id == payload.work_ticket_id).first():
        raise HTTPException(404, "关联工作票不存在")

    if payload.movement_type == StockMovementType.IN:
        p.stock_qty = (p.stock_qty or Decimal("0")) + payload.qty
    elif payload.movement_type == StockMovementType.OUT:
        if (p.stock_qty or Decimal("0")) < payload.qty:
            raise HTTPException(400, f"库存不足，当前 {p.stock_qty}")
        p.stock_qty = p.stock_qty - payload.qty
    else:  # ADJUST：直接置为 qty
        p.stock_qty = payload.qty

    m = StockMovement(
        spare_part_id=p.id,
        movement_type=payload.movement_type,
        qty=payload.qty,
        defect_id=payload.defect_id,
        work_ticket_id=payload.work_ticket_id,
        operator=current.username,
        notes=payload.notes,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return api_response(message="出入库已登记", data={
        "movement": _mv_to_dict(m),
        "stock_qty": float(p.stock_qty),
        "low_stock": float(p.stock_qty) < float(p.min_qty or 0),
    })


@router.get("/{pid}/movements")
def list_movements(
    pid: int, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    if not db.query(SparePart).filter(SparePart.id == pid).first():
        raise HTTPException(404, "物料不存在")
    q = db.query(StockMovement).options(joinedload(StockMovement.spare_part)).filter(StockMovement.spare_part_id == pid)
    total = q.count()
    rows = q.order_by(StockMovement.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return api_response(data=paginate_response([_mv_to_dict(r) for r in rows], total, page, page_size))


@router.get("/stats/overview")
def stats_overview(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    total = db.query(func.count(SparePart.id)).scalar() or 0
    low = db.query(func.count(SparePart.id)).filter(SparePart.stock_qty < SparePart.min_qty).scalar() or 0
    total_value = db.query(func.sum(SparePart.stock_qty * SparePart.unit_price)).scalar() or 0
    return api_response(data={
        "total_items": total,
        "low_stock_items": low,
        "total_value": float(total_value),
    })
