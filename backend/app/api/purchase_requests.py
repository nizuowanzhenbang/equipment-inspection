"""采购申请单 API（v3.0）

流程：DRAFT → SUBMITTED → APPROVED/REJECTED → SENT（推送 fuel-procurement）→ RECEIVED（入库回填）
"""
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_current_user, require_write, require_supervisor
from app.models.purchase_request import PurchaseRequest, PRStatus, PRSource
from app.models.spare_part import SparePart, StockMovement, StockMovementType
from app.models.user import User
from app.utils.helpers import api_response, paginate_response, generate_pr_no
from app.utils.audit import log as audit_log
from app.integration.procurement_client import push_request

router = APIRouter(prefix="/api/purchase-requests", tags=["采购申请"])


class PRCreate(BaseModel):
    spare_part_id: int
    qty: float
    urgency: str = "NORMAL"
    reason: Optional[str] = None


class PRApprove(BaseModel):
    notes: Optional[str] = None


class PRReject(BaseModel):
    reason: str


class PRReceive(BaseModel):
    received_qty: float


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


def _next_pr_seq(db: Session) -> int:
    today = datetime.utcnow().date()
    n = (
        db.query(func.count(PurchaseRequest.id))
        .filter(func.date(PurchaseRequest.created_at) == today)
        .scalar() or 0
    )
    return n + 1


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
    sp = db.query(SparePart).filter(SparePart.id == payload.spare_part_id).first()
    if not sp:
        raise HTTPException(404, "备件不存在")
    if payload.qty <= 0:
        raise HTTPException(400, "采购数量必须大于 0")
    pr = PurchaseRequest(
        pr_no=generate_pr_no(_next_pr_seq(db)),
        spare_part_id=sp.id,
        qty=payload.qty,
        estimated_amount=float(payload.qty) * float(sp.unit_price or 0),
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
    candidates = db.query(SparePart).filter(SparePart.stock_qty < SparePart.min_qty).all()
    created: List[dict] = []
    in_flight_statuses = (PRStatus.DRAFT, PRStatus.SUBMITTED, PRStatus.APPROVED, PRStatus.SENT)
    for sp in candidates:
        exists = (
            db.query(PurchaseRequest)
            .filter(PurchaseRequest.spare_part_id == sp.id, PurchaseRequest.status.in_(in_flight_statuses))
            .first()
        )
        if exists:
            continue
        suggested_qty = max(float(sp.min_qty or 0) * 2 - float(sp.stock_qty or 0), float(sp.min_qty or 0))
        pr = PurchaseRequest(
            pr_no=generate_pr_no(_next_pr_seq(db)),
            spare_part_id=sp.id,
            qty=suggested_qty,
            estimated_amount=suggested_qty * float(sp.unit_price or 0),
            urgency="URGENT" if float(sp.stock_qty or 0) <= 0 else "NORMAL",
            reason=f"低库存自动触发：当前 {sp.stock_qty}，安全 {sp.min_qty}",
            source=PRSource.AUTO_LOW_STOCK,
            status=PRStatus.SUBMITTED,
            applicant=current.username,
            submitted_at=datetime.utcnow(),
        )
        db.add(pr)
        db.flush()
        created.append({"pr_no": pr.pr_no, "spare_part_code": sp.code, "qty": suggested_qty})
    db.commit()
    audit_log(db, actor=current.username, action="pr.auto_generate",
              target_type="PurchaseRequest", summary=f"自动生成 {len(created)} 张采购申请")
    return api_response(message=f"已生成 {len(created)} 张", data={"created": created})


@router.get("/{pid}")
def get_pr(pid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    pr = db.query(PurchaseRequest).options(joinedload(PurchaseRequest.spare_part)).filter(PurchaseRequest.id == pid).first()
    if not pr:
        raise HTTPException(404, "采购申请不存在")
    return api_response(data=_to_dict(pr))


@router.post("/{pid}/submit")
def submit_pr(pid: int, db: Session = Depends(get_db), current: User = Depends(require_write)):
    pr = db.query(PurchaseRequest).filter(PurchaseRequest.id == pid).first()
    if not pr:
        raise HTTPException(404, "采购申请不存在")
    if pr.status != PRStatus.DRAFT:
        raise HTTPException(400, f"状态 {pr.status.value} 不可提交")
    pr.status = PRStatus.SUBMITTED
    pr.submitted_at = datetime.utcnow()
    db.commit()
    return api_response(message="已提交")


@router.post("/{pid}/approve")
def approve_pr(pid: int, payload: PRApprove, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    pr = db.query(PurchaseRequest).options(joinedload(PurchaseRequest.spare_part)).filter(PurchaseRequest.id == pid).first()
    if not pr:
        raise HTTPException(404, "采购申请不存在")
    if pr.status != PRStatus.SUBMITTED:
        raise HTTPException(400, f"状态 {pr.status.value} 不可批准")
    pr.status = PRStatus.APPROVED
    pr.approver = current.username
    pr.approved_at = datetime.utcnow()
    db.commit()
    audit_log(db, actor=current.username, action="pr.approve",
              target_type="PurchaseRequest", target_id=pr.id, target_no=pr.pr_no,
              summary=f"批准采购：{pr.spare_part.code if pr.spare_part else ''} × {pr.qty}")
    db.commit()
    return api_response(message="已批准")


@router.post("/{pid}/reject")
def reject_pr(pid: int, payload: PRReject, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    pr = db.query(PurchaseRequest).filter(PurchaseRequest.id == pid).first()
    if not pr:
        raise HTTPException(404, "采购申请不存在")
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
    pr = db.query(PurchaseRequest).options(joinedload(PurchaseRequest.spare_part)).filter(PurchaseRequest.id == pid).first()
    if not pr:
        raise HTTPException(404, "采购申请不存在")
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
    pr = db.query(PurchaseRequest).options(joinedload(PurchaseRequest.spare_part)).filter(PurchaseRequest.id == pid).first()
    if not pr:
        raise HTTPException(404, "采购申请不存在")
    if pr.status not in (PRStatus.SENT, PRStatus.APPROVED):
        raise HTTPException(400, f"状态 {pr.status.value} 不可收货入库")
    sp = pr.spare_part
    if not sp:
        raise HTTPException(404, "对应备件已被删除")
    if payload.received_qty <= 0:
        raise HTTPException(400, "入库数量必须 > 0")
    mv = StockMovement(
        spare_part_id=sp.id,
        movement_type=StockMovementType.IN,
        qty=payload.received_qty,
        operator=current.username,
        notes=f"采购单 {pr.pr_no} 到货入库",
    )
    sp.stock_qty = float(sp.stock_qty or 0) + float(payload.received_qty)
    pr.received_at = datetime.utcnow()
    pr.received_qty = float(pr.received_qty or 0) + float(payload.received_qty)
    if pr.received_qty >= float(pr.qty or 0):
        pr.status = PRStatus.RECEIVED
    db.add(mv)
    db.commit()
    return api_response(message="入库已登记", data={
        "stock_qty": float(sp.stock_qty),
        "status": pr.status.value,
    })


@router.post("/{pid}/cancel")
def cancel_pr(pid: int, db: Session = Depends(get_db), _: User = Depends(require_supervisor)):
    pr = db.query(PurchaseRequest).filter(PurchaseRequest.id == pid).first()
    if not pr:
        raise HTTPException(404, "采购申请不存在")
    if pr.status in (PRStatus.RECEIVED, PRStatus.CANCELLED):
        raise HTTPException(400, f"状态 {pr.status.value} 不可取消")
    pr.status = PRStatus.CANCELLED
    db.commit()
    return api_response(message="已取消")
