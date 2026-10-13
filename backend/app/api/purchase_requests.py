"""采购申请单 API（v3.0）

流程：DRAFT → SUBMITTED → APPROVED/REJECTED → SENT（推送 fuel-procurement）→ RECEIVED（入库回填）
"""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Optional
from math import isfinite
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_current_user, require_write, require_supervisor
from app.models.purchase_request import PurchaseRequest, PurchaseReceipt, PRStatus, PRSource
from app.models.spare_part import SparePart, StockMovement, StockMovementType
from app.models.user import User
from app.schemas.spare_part import InventoryDecimal, MAX_STOCK_QUANTITY
from app.utils.helpers import api_response, paginate_response
from app.utils.audit import log as audit_log
from app.utils.transactions import lock_spare_part
from app.integration.procurement_client import push_request
from app.services.purchases import allocate_purchase_number, estimated_amount, generate_low_stock

router = APIRouter(prefix="/api/purchase-requests", tags=["采购申请"])


def normalize_nonfinite(value):
    return str(value) if isinstance(value, float) and not isfinite(value) else value


PurchaseQuantity = Annotated[InventoryDecimal, Field(gt=0), BeforeValidator(normalize_nonfinite)]


class PRCreate(BaseModel):
    spare_part_id: int
    qty: PurchaseQuantity
    urgency: Literal["NORMAL", "URGENT"] = "NORMAL"
    reason: Optional[str] = None


class PRApprove(BaseModel):
    notes: Optional[str] = None


class PRReject(BaseModel):
    reason: str


class PRReceive(BaseModel):
    received_qty: InventoryDecimal
    request_id: Optional[UUID] = None


class PRResponse(BaseModel):
    id: int
    pr_no: str
    spare_part_id: int
    spare_part_code: Optional[str] = None
    spare_part_name: Optional[str] = None
    qty: float
    estimated_amount: float
    urgency: str
    reason: Optional[str]
    source: PRSource
    status: PRStatus
    applicant: Optional[str]
    approver: Optional[str]
    submitted_at: Optional[datetime]
    approved_at: Optional[datetime]
    rejected_reason: Optional[str]
    external_order_no: Optional[str]
    sent_at: Optional[datetime]
    received_at: Optional[datetime]
    received_qty: float
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


def _to_dict(pr: PurchaseRequest) -> dict:
    d = PRResponse.model_validate(pr).model_dump(mode="json")
    if pr.spare_part:
        d["spare_part_code"] = pr.spare_part.code
        d["spare_part_name"] = pr.spare_part.name
    return d


@router.get("")
def list_prs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[PRStatus] = None,
    source: Optional[PRSource] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(PurchaseRequest).options(joinedload(PurchaseRequest.spare_part))
    if status:
        q = q.filter(PurchaseRequest.status == status)
    if source:
        q = q.filter(PurchaseRequest.source == source)
    total = q.count()
    rows = q.order_by(PurchaseRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return api_response(data=paginate_response([_to_dict(r) for r in rows], total, page, page_size))


@router.post("")
def create_pr(payload: PRCreate, db: Session = Depends(get_db), current: User = Depends(require_write)):
    sp = lock_spare_part(db, payload.spare_part_id)
    if not sp:
        raise HTTPException(404, "备件不存在")
    amount = estimated_amount(payload.qty, sp.unit_price)
    pr = PurchaseRequest(
        pr_no=allocate_purchase_number(db),
        spare_part_id=sp.id,
        qty=payload.qty,
        estimated_amount=amount,
        urgency=payload.urgency,
        reason=payload.reason,
        source=PRSource.MANUAL,
        status=PRStatus.DRAFT,
        applicant=current.username,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return api_response(message="采购申请已创建", data=_to_dict(pr))


@router.post("/auto-generate")
def auto_generate(db: Session = Depends(get_db), current: User = Depends(require_write)):
    """扫描所有低库存备件，没有 in-flight 申请的自动建一张草稿"""
    result = generate_low_stock(db, current.username)
    audit_log(db, actor=current.username, action="pr.auto_generate",
              target_type="PurchaseRequest", summary=f"自动生成 {len(result['created'])} 张采购申请，跳过 {len(result['skipped'])} 项")
    db.commit()
    return api_response(message=f"已生成 {len(result['created'])} 张，跳过 {len(result['skipped'])} 项", data=result)


@router.get("/{pid}")
def get_pr(pid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    pr = db.query(PurchaseRequest).options(joinedload(PurchaseRequest.spare_part)).filter(PurchaseRequest.id == pid).first()
    if not pr:
        raise HTTPException(404, "采购申请不存在")
    return api_response(data=_to_dict(pr))


def _lock_pr(db: Session, pid: int) -> PurchaseRequest:
    """All existing order transitions share the inventory lock, then refresh state."""
    pr = db.query(PurchaseRequest).options(joinedload(PurchaseRequest.spare_part)).filter(PurchaseRequest.id == pid).first()
    if not pr:
        raise HTTPException(404, "采购申请不存在")
    if not lock_spare_part(db, pr.spare_part_id):
        raise HTTPException(404, "对应备件已被删除")
    # Waiting for the part lock may have made both the order and its relation stale.
    pr = (db.query(PurchaseRequest).options(joinedload(PurchaseRequest.spare_part))
          .filter(PurchaseRequest.id == pid).populate_existing().first())
    if not pr:
        raise HTTPException(404, "采购申请不存在")
    return pr


@router.post("/{pid}/submit")
def submit_pr(pid: int, db: Session = Depends(get_db), current: User = Depends(require_write)):
    pr = _lock_pr(db, pid)
    if pr.status != PRStatus.DRAFT:
        raise HTTPException(400, f"状态 {pr.status.value} 不可提交")
    pr.status = PRStatus.SUBMITTED
    pr.submitted_at = datetime.utcnow()
    db.commit()
    return api_response(message="已提交")


@router.post("/{pid}/approve")
def approve_pr(pid: int, payload: PRApprove, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    pr = _lock_pr(db, pid)
    if pr.status != PRStatus.SUBMITTED:
        raise HTTPException(400, f"状态 {pr.status.value} 不可批准")
    pr.status = PRStatus.APPROVED
    pr.approver = current.username
    pr.approved_at = datetime.utcnow()
    audit_log(db, actor=current.username, action="pr.approve",
              target_type="PurchaseRequest", target_id=pr.id, target_no=pr.pr_no,
              summary=f"批准采购：{pr.spare_part.code if pr.spare_part else ''} × {pr.qty}")
    db.commit()
    return api_response(message="已批准")


@router.post("/{pid}/reject")
def reject_pr(pid: int, payload: PRReject, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    pr = _lock_pr(db, pid)
    if pr.status != PRStatus.SUBMITTED:
        raise HTTPException(400, f"状态 {pr.status.value} 不可驳回")
    pr.status = PRStatus.REJECTED
    pr.approver = current.username
    pr.rejected_reason = payload.reason
    db.commit()
    return api_response(message="已驳回")


@router.post("/{pid}/send")
def send_pr(pid: int, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    """推送 fuel-procurement"""
    pr = _lock_pr(db, pid)
    if pr.status != PRStatus.APPROVED:
        raise HTTPException(400, f"状态 {pr.status.value} 不可推送")
    result = push_request(db, pr)
    if not result["ok"]:
        raise HTTPException(400, result["message"])
    audit_log(db, actor=current.username, action="pr.send",
              target_type="PurchaseRequest", target_id=pr.id, target_no=pr.pr_no,
              summary=f"推送至采购系统：{result.get('external_order_no')}")
    db.commit()
    return api_response(message=result["message"], data={"external_order_no": result.get("external_order_no")})


@router.post("/{pid}/receive")
def receive_pr(pid: int, payload: PRReceive, db: Session = Depends(get_db), current: User = Depends(require_write)):
    """到货入库：自动写一条 StockMovement(IN) 并更新备件库存"""
    pr = _lock_pr(db, pid)
    sp = pr.spare_part
    request_id = str(payload.request_id) if payload.request_id is not None else None
    if request_id is not None:
        recorded = db.query(PurchaseReceipt).filter(
            PurchaseReceipt.purchase_request_id == pid,
            PurchaseReceipt.request_id == request_id,
        ).first()
        if recorded:
            if recorded.actor_id != current.id or recorded.qty != payload.received_qty:
                raise HTTPException(409, "该收货请求标识已用于其他数量或操作人")
            return api_response(message="入库已登记", data={
                "stock_qty": float(recorded.stock_qty_after),
                "status": recorded.status_after,
            })
    if pr.status not in (PRStatus.SENT, PRStatus.APPROVED):
        raise HTTPException(400, f"状态 {pr.status.value} 不可收货入库")
    if payload.received_qty <= 0:
        raise HTTPException(400, "入库数量必须 > 0")
    quantity = payload.received_qty
    new_stock = (sp.stock_qty or Decimal("0")) + quantity
    new_received = (pr.received_qty or Decimal("0")) + quantity
    if new_stock > MAX_STOCK_QUANTITY or new_received > MAX_STOCK_QUANTITY:
        raise HTTPException(400, "累计库存或收货数量超出上限")
    if new_received > pr.qty:
        raise HTTPException(409, "到货数量超过采购单剩余数量，请另行核对额外到货")
    mv = StockMovement(
        spare_part_id=sp.id,
        movement_type=StockMovementType.IN,
        qty=quantity,
        operator=current.username,
        notes=f"采购单 {pr.pr_no} 到货入库",
    )
    sp.stock_qty = new_stock
    pr.received_at = datetime.utcnow()
    pr.received_qty = new_received
    if pr.received_qty >= (pr.qty or Decimal("0")):
        pr.status = PRStatus.RECEIVED
    db.add(mv)
    if request_id is not None:
        db.flush()
        db.add(PurchaseReceipt(
            purchase_request_id=pid, request_id=request_id, actor_id=current.id,
            qty=quantity, movement_id=mv.id, stock_qty_after=new_stock,
            status_after=pr.status.value,
        ))
    # Build from the locked transaction snapshot before commit expires ORM state.
    # Another receipt may commit before this HTTP response is serialized.
    result = {"stock_qty": float(new_stock), "status": pr.status.value}
    db.commit()
    return api_response(message="入库已登记", data=result)


@router.post("/{pid}/cancel")
def cancel_pr(pid: int, db: Session = Depends(get_db), _: User = Depends(require_supervisor)):
    pr = _lock_pr(db, pid)
    if pr.status in (PRStatus.RECEIVED, PRStatus.CANCELLED):
        raise HTTPException(400, f"状态 {pr.status.value} 不可取消")
    pr.status = PRStatus.CANCELLED
    db.commit()
    return api_response(message="已取消")
