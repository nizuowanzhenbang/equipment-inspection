"""工作票 API：DRAFT → SUBMITTED → ISSUED → IN_WORK → COMPLETED → CLOSED"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_current_user, require_write, require_supervisor, require_repairman
from app.models.equipment import Equipment, EquipmentStatus
from app.models.defect import Defect
from app.models.ticket import WorkTicket, WorkTicketStatus, WorkTicketType
from app.models.user import User
from app.schemas.ticket import (
    WorkTicketCreate, WorkTicketUpdate, WorkTicketIssue,
    WorkTicketPermit, WorkTicketComplete, WorkTicketClose, WorkTicketResponse,
)
from app.utils.helpers import api_response, paginate_response, generate_work_ticket_no
from app.utils.audit import log as audit_log
from app.utils.signature import assert_password, append_signature, make_signature, verify_signature

router = APIRouter(prefix="/api/work-tickets", tags=["工作票"])


def _to_dict(w: WorkTicket) -> dict:
    data = WorkTicketResponse.model_validate(w).model_dump(mode="json")
    if w.equipment:
        data["equipment_name"] = w.equipment.name
        data["equipment_code"] = w.equipment.code
    if w.defect:
        data["defect_no"] = w.defect.defect_no
    return data


@router.get("")
def list_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[WorkTicketStatus] = None,
    ticket_type: Optional[WorkTicketType] = None,
    equipment_id: Optional[int] = None,
    defect_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(WorkTicket).options(joinedload(WorkTicket.equipment), joinedload(WorkTicket.defect))
    if status:
        q = q.filter(WorkTicket.status == status)
    if ticket_type:
        q = q.filter(WorkTicket.ticket_type == ticket_type)
    if equipment_id:
        q = q.filter(WorkTicket.equipment_id == equipment_id)
    if defect_id:
        q = q.filter(WorkTicket.defect_id == defect_id)
    total = q.count()
    rows = q.order_by(WorkTicket.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return api_response(data=paginate_response([_to_dict(r) for r in rows], total, page, page_size))


@router.post("")
def create_ticket(payload: WorkTicketCreate, db: Session = Depends(get_db), current: User = Depends(require_write)):
    eq = db.query(Equipment).filter(Equipment.id == payload.equipment_id).first()
    if not eq:
        raise HTTPException(404, "设备不存在")
    if payload.defect_id:
        d = db.query(Defect).filter(Defect.id == payload.defect_id).first()
        if not d:
            raise HTTPException(404, "关联缺陷不存在")
        if d.equipment_id != eq.id:
            raise HTTPException(400, "缺陷的设备与工作票设备不一致")

    next_seq = (
        db.query(func.count(WorkTicket.id))
        .filter(func.date(WorkTicket.created_at) == datetime.utcnow().date())
        .scalar() or 0
    ) + 1
    w = WorkTicket(
        ticket_no=generate_work_ticket_no(next_seq),
        ticket_type=payload.ticket_type,
        defect_id=payload.defect_id,
        equipment_id=payload.equipment_id,
        work_content=payload.work_content,
        safety_measures=payload.safety_measures or [],
        risk_notes=payload.risk_notes,
        planned_start=payload.planned_start,
        planned_end=payload.planned_end,
        applicant=current.username,
        principal=payload.principal,
        team_members=payload.team_members or [],
        status=WorkTicketStatus.DRAFT,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return api_response(message="工作票已起草", data=_to_dict(w))


@router.get("/{wid}")
def get_ticket(wid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    w = db.query(WorkTicket).options(joinedload(WorkTicket.equipment), joinedload(WorkTicket.defect)).filter(WorkTicket.id == wid).first()
    if not w:
        raise HTTPException(404, "工作票不存在")
    return api_response(data=_to_dict(w))


@router.put("/{wid}")
def update_ticket(wid: int, payload: WorkTicketUpdate, db: Session = Depends(get_db), _: User = Depends(require_write)):
    w = db.query(WorkTicket).filter(WorkTicket.id == wid).first()
    if not w:
        raise HTTPException(404, "工作票不存在")
    if w.status not in (WorkTicketStatus.DRAFT, WorkTicketStatus.SUBMITTED):
        raise HTTPException(400, f"状态 {w.status.value} 不可编辑")
    for f, v in payload.model_dump(exclude_unset=True).items():
        setattr(w, f, v)
    db.commit()
    db.refresh(w)
    return api_response(message="已更新", data=_to_dict(w))


@router.post("/{wid}/submit")
def submit(wid: int, db: Session = Depends(get_db), _: User = Depends(require_write)):
    w = db.query(WorkTicket).filter(WorkTicket.id == wid).first()
    if not w:
        raise HTTPException(404, "工作票不存在")
    if w.status != WorkTicketStatus.DRAFT:
        raise HTTPException(400, f"状态 {w.status.value} 不可提交")
    if not w.principal or not w.work_content:
        raise HTTPException(400, "工作负责人/工作内容必填")
    w.status = WorkTicketStatus.SUBMITTED
    w.submitted_at = datetime.utcnow()
    db.commit()
    return api_response(message="已提交，待签发")


@router.post("/{wid}/issue")
def issue(wid: int, payload: WorkTicketIssue, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    w = db.query(WorkTicket).options(joinedload(WorkTicket.equipment)).filter(WorkTicket.id == wid).first()
    if not w:
        raise HTTPException(404, "工作票不存在")
    if w.status != WorkTicketStatus.SUBMITTED:
        raise HTTPException(400, f"状态 {w.status.value} 不可签发")
    assert_password(current, payload.signature_password)
    w.status = WorkTicketStatus.ISSUED
    w.issuer = current.username
    w.issued_at = datetime.utcnow()
    w.approval_notes = payload.approval_notes
    sig = make_signature(w.ticket_no, "issue", current.username)
    w.signatures = append_signature(w.signatures, sig)
    audit_log(db, actor=current.username, action="wt.issue",
              target_type="WorkTicket", target_id=w.id, target_no=w.ticket_no,
              summary=f"签发：{w.work_content[:60]}（sig {sig['sig_hash'][:8]}）")
    db.commit()
    return api_response(message="已签发", data={"signature": sig})


@router.post("/{wid}/permit")
def permit(wid: int, payload: WorkTicketPermit, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    """许可工作：设备转检修态，工作票进入 IN_WORK"""
    w = db.query(WorkTicket).options(joinedload(WorkTicket.equipment)).filter(WorkTicket.id == wid).first()
    if not w:
        raise HTTPException(404, "工作票不存在")
    if w.status != WorkTicketStatus.ISSUED:
        raise HTTPException(400, f"状态 {w.status.value} 不可许可")
    assert_password(current, payload.signature_password)
    w.status = WorkTicketStatus.IN_WORK
    w.permitter = payload.permitter or current.username
    w.permitted_at = datetime.utcnow()
    w.actual_start = datetime.utcnow()
    # 设备转检修
    if w.equipment and w.equipment.status == EquipmentStatus.RUNNING:
        w.equipment.status = EquipmentStatus.MAINTENANCE
    sig = make_signature(w.ticket_no, "permit", current.username)
    w.signatures = append_signature(w.signatures, sig)
    audit_log(db, actor=current.username, action="wt.permit",
              target_type="WorkTicket", target_id=w.id, target_no=w.ticket_no,
              summary=f"许可开工 → {w.equipment.code if w.equipment else ''} 转检修（sig {sig['sig_hash'][:8]}）")
    db.commit()
    return api_response(message="已许可，作业开始", data={"signature": sig})


@router.post("/{wid}/complete")
def complete(wid: int, payload: WorkTicketComplete, db: Session = Depends(get_db), current: User = Depends(require_repairman)):
    """工作终结：填写收尾，等待收票"""
    w = db.query(WorkTicket).filter(WorkTicket.id == wid).first()
    if not w:
        raise HTTPException(404, "工作票不存在")
    if w.status != WorkTicketStatus.IN_WORK:
        raise HTTPException(400, f"状态 {w.status.value} 不可终结")
    assert_password(current, payload.signature_password)
    w.status = WorkTicketStatus.COMPLETED
    w.actual_end = datetime.utcnow()
    w.completed_at = datetime.utcnow()
    w.closing_notes = payload.closing_notes
    sig = make_signature(w.ticket_no, "complete", current.username)
    w.signatures = append_signature(w.signatures, sig)
    db.commit()
    return api_response(message="工作终结", data={"signature": sig})


@router.post("/{wid}/close")
def close_ticket(wid: int, payload: WorkTicketClose, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    """收票归档：设备如无其他未结缺陷/票则恢复运行"""
    w = db.query(WorkTicket).options(joinedload(WorkTicket.equipment)).filter(WorkTicket.id == wid).first()
    if not w:
        raise HTTPException(404, "工作票不存在")
    if w.status != WorkTicketStatus.COMPLETED:
        raise HTTPException(400, f"状态 {w.status.value} 不可归档")
    assert_password(current, payload.signature_password)
    w.status = WorkTicketStatus.CLOSED
    w.closed_at = datetime.utcnow()
    sig = make_signature(w.ticket_no, "close", current.username)
    w.signatures = append_signature(w.signatures, sig)
    # 设备恢复运行（如无其他未结工作票）
    if w.equipment and w.equipment.status == EquipmentStatus.MAINTENANCE:
        other = (
            db.query(func.count(WorkTicket.id))
            .filter(
                WorkTicket.equipment_id == w.equipment.id,
                WorkTicket.id != w.id,
                WorkTicket.status.in_([WorkTicketStatus.IN_WORK, WorkTicketStatus.ISSUED]),
            )
            .scalar() or 0
        )
        if other == 0:
            w.equipment.status = EquipmentStatus.RUNNING
    audit_log(db, actor=current.username, action="wt.close",
              target_type="WorkTicket", target_id=w.id, target_no=w.ticket_no,
              summary=f"收票归档：{w.work_content[:60]}（sig {sig['sig_hash'][:8]}）")
    db.commit()
    return api_response(message="工作票已收回归档", data={"signature": sig})


@router.get("/{wid}/signatures/verify")
def verify_signatures(wid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """重算 HMAC 校验签名链是否被篡改"""
    w = db.query(WorkTicket).filter(WorkTicket.id == wid).first()
    if not w:
        raise HTTPException(404, "工作票不存在")
    chain = list(w.signatures or [])
    results = [
        {**entry, "valid": verify_signature(entry, w.ticket_no)}
        for entry in chain
    ]
    all_ok = all(r["valid"] for r in results) if results else True
    return api_response(data={"ticket_no": w.ticket_no, "all_valid": all_ok, "signatures": results})


@router.post("/{wid}/cancel")
def cancel(wid: int, db: Session = Depends(get_db), _: User = Depends(require_supervisor)):
    w = db.query(WorkTicket).filter(WorkTicket.id == wid).first()
    if not w:
        raise HTTPException(404, "工作票不存在")
    if w.status in (WorkTicketStatus.CLOSED, WorkTicketStatus.COMPLETED):
        raise HTTPException(400, "已完成/归档工作票不可取消")
    w.status = WorkTicketStatus.CANCELLED
    db.commit()
    return api_response(message="已取消")


@router.post("/{wid}/check-safety")
def check_safety_step(wid: int, step_seq: int, db: Session = Depends(get_db), current: User = Depends(require_repairman)):
    """勾选某条安全措施（safety_measures 数组中按 seq 找）"""
    w = db.query(WorkTicket).filter(WorkTicket.id == wid).first()
    if not w:
        raise HTTPException(404, "工作票不存在")
    if w.status not in (WorkTicketStatus.ISSUED, WorkTicketStatus.IN_WORK):
        raise HTTPException(400, "仅签发或作业中的票可勾选安全措施")
    measures = list(w.safety_measures or [])
    found = False
    for m in measures:
        if m.get("seq") == step_seq:
            m["checked"] = True
            m["checked_by"] = current.username
            m["checked_at"] = datetime.utcnow().isoformat()
            found = True
            break
    if not found:
        raise HTTPException(400, f"未找到 seq={step_seq} 的安全措施")
    w.safety_measures = measures
    db.commit()
    return api_response(message="已勾选")
