"""操作票 API：DRAFT → REVIEWED → APPROVED → EXECUTING → COMPLETED"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db, get_current_user, require_write, require_supervisor, require_inspector
from app.models.equipment import Equipment
from app.models.ticket import (
    OperationTicket, OperationTicketStatus, OperationTicketType,
    WorkTicket, OperationTemplate,
)
from app.models.user import User
from app.schemas.ticket import (
    OperationTicketCreate, OperationTicketUpdate, StepExecute, OperationTicketResponse,
    OperationTemplateCreate, OperationTemplateResponse, OpReview, OpApprove,
)
from app.utils.helpers import api_response, paginate_response, generate_operation_ticket_no
from app.utils.signature import assert_password, append_signature, make_signature, verify_signature

router = APIRouter(prefix="/api/operation-tickets", tags=["操作票"])


# ---- 模板 API（必须在 /{oid} 之前注册以避免冲突）----
@router.get("/templates")
def list_templates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.query(OperationTemplate).order_by(OperationTemplate.use_count.desc()).all()
    return api_response(data=[OperationTemplateResponse.model_validate(r).model_dump(mode="json") for r in rows])


@router.post("/templates")
def create_template(payload: OperationTemplateCreate, db: Session = Depends(get_db), current: User = Depends(require_write)):
    if db.query(OperationTemplate).filter(OperationTemplate.name == payload.name).first():
        raise HTTPException(400, f"模板名 {payload.name} 已存在")
    if not payload.steps:
        raise HTTPException(400, "至少要有一条步骤")
    steps = []
    for i, s in enumerate(payload.steps, 1):
        s = dict(s)
        s["seq"] = s.get("seq") or i
        s.setdefault("expected", None)
        steps.append({"seq": s["seq"], "action": s.get("action", ""), "expected": s.get("expected")})
    t = OperationTemplate(
        name=payload.name,
        operation_type=payload.operation_type,
        description=payload.description,
        steps=steps,
        created_by=current.username,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return api_response(message="模板已创建", data=OperationTemplateResponse.model_validate(t).model_dump(mode="json"))


@router.post("/templates/from-ticket/{oid}")
def save_as_template(oid: int, name: str, description: Optional[str] = None, db: Session = Depends(get_db), current: User = Depends(require_write)):
    """把现有操作票另存为模板（去掉执行结果字段）"""
    o = db.query(OperationTicket).filter(OperationTicket.id == oid).first()
    if not o:
        raise HTTPException(404, "操作票不存在")
    if db.query(OperationTemplate).filter(OperationTemplate.name == name).first():
        raise HTTPException(400, f"模板名 {name} 已存在")
    steps_clean = [
        {"seq": s.get("seq"), "action": s.get("action"), "expected": s.get("expected")}
        for s in (o.steps or [])
    ]
    t = OperationTemplate(
        name=name,
        operation_type=o.operation_type,
        description=description or f"由操作票 {o.ticket_no} 另存",
        steps=steps_clean,
        created_by=current.username,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return api_response(message="已另存为模板", data=OperationTemplateResponse.model_validate(t).model_dump(mode="json"))


@router.delete("/templates/{tid}")
def delete_template(tid: int, db: Session = Depends(get_db), _: User = Depends(require_supervisor)):
    t = db.query(OperationTemplate).filter(OperationTemplate.id == tid).first()
    if not t:
        raise HTTPException(404, "模板不存在")
    db.delete(t)
    db.commit()
    return api_response(message="已删除")


def _to_dict(o: OperationTicket) -> dict:
    data = OperationTicketResponse.model_validate(o).model_dump(mode="json")
    if o.equipment:
        data["equipment_name"] = o.equipment.name
    return data


@router.get("")
def list_tickets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[OperationTicketStatus] = None,
    operation_type: Optional[OperationTicketType] = None,
    work_ticket_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(OperationTicket).options(joinedload(OperationTicket.equipment))
    if status:
        q = q.filter(OperationTicket.status == status)
    if operation_type:
        q = q.filter(OperationTicket.operation_type == operation_type)
    if work_ticket_id:
        q = q.filter(OperationTicket.work_ticket_id == work_ticket_id)
    total = q.count()
    rows = q.order_by(OperationTicket.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return api_response(data=paginate_response([_to_dict(r) for r in rows], total, page, page_size))


@router.post("")
def create_ticket(payload: OperationTicketCreate, db: Session = Depends(get_db), current: User = Depends(require_write)):
    if payload.work_ticket_id:
        if not db.query(WorkTicket).filter(WorkTicket.id == payload.work_ticket_id).first():
            raise HTTPException(404, "关联工作票不存在")
    if payload.equipment_id:
        if not db.query(Equipment).filter(Equipment.id == payload.equipment_id).first():
            raise HTTPException(404, "设备不存在")

    # 来源：steps 或 template_id 二选一
    raw_steps = payload.steps
    template = None
    if payload.template_id and not raw_steps:
        template = db.query(OperationTemplate).filter(OperationTemplate.id == payload.template_id).first()
        if not template:
            raise HTTPException(404, "模板不存在")
        raw_steps = template.steps

    if not raw_steps:
        raise HTTPException(400, "至少要有一条操作步骤（或选用模板）")

    # 规范化步骤 seq
    steps = []
    for i, s in enumerate(raw_steps, 1):
        s = dict(s)
        s["seq"] = s.get("seq") or i
        s.setdefault("expected", None)
        s.setdefault("executed_at", None)
        s.setdefault("executed_by", None)
        s.setdefault("result", None)
        s.setdefault("notes", None)
        steps.append(s)

    next_seq = (
        db.query(func.count(OperationTicket.id))
        .filter(func.date(OperationTicket.created_at) == datetime.utcnow().date())
        .scalar() or 0
    ) + 1
    o = OperationTicket(
        ticket_no=generate_operation_ticket_no(next_seq),
        title=payload.title,
        operation_type=payload.operation_type,
        work_ticket_id=payload.work_ticket_id,
        equipment_id=payload.equipment_id,
        operator=payload.operator or current.username,
        supervisor=payload.supervisor,
        steps=steps,
        status=OperationTicketStatus.DRAFT,
        notes=payload.notes,
    )
    db.add(o)
    if template is not None:
        template.use_count = (template.use_count or 0) + 1
    db.commit()
    db.refresh(o)
    return api_response(message="操作票已起草", data=_to_dict(o))


@router.get("/{oid}")
def get_ticket(oid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    o = db.query(OperationTicket).options(joinedload(OperationTicket.equipment)).filter(OperationTicket.id == oid).first()
    if not o:
        raise HTTPException(404, "操作票不存在")
    return api_response(data=_to_dict(o))


@router.put("/{oid}")
def update_ticket(oid: int, payload: OperationTicketUpdate, db: Session = Depends(get_db), _: User = Depends(require_write)):
    o = db.query(OperationTicket).filter(OperationTicket.id == oid).first()
    if not o:
        raise HTTPException(404, "操作票不存在")
    if o.status != OperationTicketStatus.DRAFT:
        raise HTTPException(400, f"状态 {o.status.value} 不可编辑")
    for f, v in payload.model_dump(exclude_unset=True).items():
        setattr(o, f, v)
    db.commit()
    db.refresh(o)
    return api_response(message="已更新", data=_to_dict(o))


@router.post("/{oid}/review")
def review(oid: int, payload: OpReview, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    o = db.query(OperationTicket).filter(OperationTicket.id == oid).first()
    if not o:
        raise HTTPException(404, "操作票不存在")
    if o.status != OperationTicketStatus.DRAFT:
        raise HTTPException(400, f"状态 {o.status.value} 不可审核")
    assert_password(current, payload.signature_password)
    o.status = OperationTicketStatus.REVIEWED
    o.supervisor = o.supervisor or current.username
    o.reviewed_at = datetime.utcnow()
    sig = make_signature(o.ticket_no, "review", current.username)
    o.signatures = append_signature(o.signatures, sig)
    db.commit()
    return api_response(message="已审核", data={"signature": sig})


@router.post("/{oid}/approve")
def approve(oid: int, payload: OpApprove, db: Session = Depends(get_db), current: User = Depends(require_supervisor)):
    o = db.query(OperationTicket).filter(OperationTicket.id == oid).first()
    if not o:
        raise HTTPException(404, "操作票不存在")
    if o.status != OperationTicketStatus.REVIEWED:
        raise HTTPException(400, f"状态 {o.status.value} 不可批准")
    assert_password(current, payload.signature_password)
    o.status = OperationTicketStatus.APPROVED
    o.approver = current.username
    o.approved_at = datetime.utcnow()
    sig = make_signature(o.ticket_no, "approve", current.username)
    o.signatures = append_signature(o.signatures, sig)
    db.commit()
    return api_response(message="已批准", data={"signature": sig})


@router.post("/{oid}/start")
def start(oid: int, db: Session = Depends(get_db), current: User = Depends(require_inspector)):
    o = db.query(OperationTicket).filter(OperationTicket.id == oid).first()
    if not o:
        raise HTTPException(404, "操作票不存在")
    if o.status != OperationTicketStatus.APPROVED:
        raise HTTPException(400, f"状态 {o.status.value} 不可开始执行")
    o.status = OperationTicketStatus.EXECUTING
    o.started_at = datetime.utcnow()
    if not o.operator:
        o.operator = current.username
    db.commit()
    return api_response(message="开始执行")


@router.post("/{oid}/execute-step")
def execute_step(oid: int, payload: StepExecute, db: Session = Depends(get_db), current: User = Depends(require_inspector)):
    """逐步执行：记录某一步操作结果"""
    o = db.query(OperationTicket).filter(OperationTicket.id == oid).first()
    if not o:
        raise HTTPException(404, "操作票不存在")
    if o.status != OperationTicketStatus.EXECUTING:
        raise HTTPException(400, f"状态 {o.status.value} 不可执行步骤")
    steps = list(o.steps or [])
    matched = None
    for s in steps:
        if s.get("seq") == payload.seq:
            matched = s
            break
    if matched is None:
        raise HTTPException(400, f"未找到 seq={payload.seq} 步骤")
    assert_password(current, payload.signature_password)
    matched["result"] = payload.result.upper()
    matched["notes"] = payload.notes
    matched["executed_by"] = current.username
    matched["executed_at"] = datetime.utcnow().isoformat()
    o.steps = steps
    # 每步执行单独签名
    step_sig = make_signature(o.ticket_no, f"step-{payload.seq}", current.username)
    matched["sig_hash"] = step_sig["sig_hash"]
    o.signatures = append_signature(o.signatures, step_sig)
    # 全部完成 → COMPLETED
    if all(s.get("result") for s in steps):
        o.status = OperationTicketStatus.COMPLETED
        o.completed_at = datetime.utcnow()
        done_sig = make_signature(o.ticket_no, "complete", current.username)
        o.signatures = append_signature(o.signatures, done_sig)
    db.commit()
    return api_response(
        message="步骤已记录" + ("（全部完成）" if o.status == OperationTicketStatus.COMPLETED else ""),
        data={"all_done": o.status == OperationTicketStatus.COMPLETED, "signature": step_sig},
    )


@router.get("/{oid}/signatures/verify")
def verify_op_signatures(oid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    o = db.query(OperationTicket).filter(OperationTicket.id == oid).first()
    if not o:
        raise HTTPException(404, "操作票不存在")
    chain = list(o.signatures or [])
    results = [
        {**entry, "valid": verify_signature(entry, o.ticket_no)}
        for entry in chain
    ]
    all_ok = all(r["valid"] for r in results) if results else True
    return api_response(data={"ticket_no": o.ticket_no, "all_valid": all_ok, "signatures": results})


@router.post("/{oid}/cancel")
def cancel(oid: int, db: Session = Depends(get_db), _: User = Depends(require_supervisor)):
    o = db.query(OperationTicket).filter(OperationTicket.id == oid).first()
    if not o:
        raise HTTPException(404, "操作票不存在")
    if o.status == OperationTicketStatus.COMPLETED:
        raise HTTPException(400, "已完成操作票不可取消")
    o.status = OperationTicketStatus.CANCELLED
    db.commit()
    return api_response(message="已取消")
